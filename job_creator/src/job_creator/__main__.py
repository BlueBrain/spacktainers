import copy
import glob
import logging
import logging.config
import os

import click
from natsort import natsorted

from job_creator.architectures import architecture_map
from job_creator.ci_objects import Job, Trigger, Workflow
from job_creator.containers import (Spacktainerizer,
                                    generate_base_container_workflow,
                                    generate_spack_containers_workflow)
from job_creator.job_templates import (clean_cache_yaml,
                                       generate_containers_workflow_yaml)
from job_creator.logging_config import LOGGING_CONFIG
from job_creator.packages import generate_packages_workflow
from job_creator.utils import (get_arch_or_multiarch_job, get_architectures,
                               load_yaml, write_yaml)

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("job_creator")


@click.group()
def jc():
    pass


@jc.command
@click.option(
    "--architecture",
    "-a",
    help="Architecture to generate spackah pipeline for",
)
@click.option(
    "--out-dir",
    "-o",
    help="Which directory to write the spackah build pipeline to",
)
def generate_spackah_workflow(architecture, out_dir):
    """
    Generate the workflow that will build the actual spack-package-based containers
    for the given container definition
    """
    os.makedirs(out_dir, exist_ok=True)
    workflow = generate_spack_containers_workflow(architecture, out_dir)
    write_yaml(workflow.to_dict(), f"{out_dir}/spackah_pipeline.yaml")


@jc.command
@click.option("--pipeline-file", "-f", help="YAML pipeline file generated by spack")
@click.option(
    "--out-dir",
    "-o",
    help="Output dir in which to dump split pipelines. Will be created if necessary.",
)
def process_spack_pipeline(pipeline_file, out_dir):
    """
    Given a spack-generated pipeline file, this will:
      * split it along the generated stages: each stage will become its own workflow
      * in each "stage", do the necessary spack mirror manipulation, variable setting, ...
      * add a job before all the stages run that will collect artifacts needed, so that
        the stages can grab them from within the same workflow
      * configure "stage" dependencies
    """
    logger.info(
        "Processing spack pipeline for pipeline file {pipeline_file} with output dir {out_dir}"
    )
    architecture = out_dir.split(".")[1]
    pipeline = load_yaml(pipeline_file)

    if "no-specs-to-rebuild" in pipeline:
        write_yaml(pipeline, "spack_pipeline.yaml")
        return

    split_pipelines = {
        stage: {"variables": pipeline["variables"]} for stage in pipeline["stages"]
    }
    for name, item in pipeline.items():
        if name == "variables" and "variables" in architecture_map[architecture]:
            item.update(architecture_map[architecture]["variables"])
        if name in ["stages", "variables"]:
            continue
        item.pop("needs", None)
        stage = item.pop("stage", "no stage")
        job = Job(name=name, architecture=architecture, **item)

        job.add_spack_mirror()
        job.set_aws_variables()

        job.image["pull_policy"] = "always"
        job.needs = [
            {
                "pipeline": os.environ.get("CI_PIPELINE_ID"),
                "job": f"generate build cache population job for {architecture}",
                "artifacts": True,
            }
        ]
        split_pipelines[stage][name] = job.to_dict()

    build_workflow = Workflow()

    os.makedirs(out_dir, exist_ok=True)

    collect_job = "collect artifacts"
    collect_job = Job(
        collect_job,
        architecture,
        needs=[
            {
                "pipeline": os.environ.get("CI_PIPELINE_ID"),
                "job": f"process spack pipeline for {architecture}",
                "artifacts": True,
            }
        ],
        script=[
            "cat spack_pipeline.yaml",
            f"find artifacts.{architecture}",
        ],
        stage="run spack-generated pipelines",
        artifacts={"when": "always", "paths": ["*.yaml", "artifacts.*"]},
    )
    build_workflow.add_job(collect_job)

    previous_stage = None
    for stage, stage_pipeline in natsorted(split_pipelines.items()):
        logger.debug(f"Adding stage {stage}")
        if len(stage_pipeline) > 1:
            pipeline_file = f"{out_dir}/pipeline-{stage}.yaml"
            needs = [
                {
                    "job": collect_job.name,
                    "artifacts": True,
                },
            ]

            if previous_stage:
                needs.append({"job": previous_stage})

            previous_stage = stage

            trigger = Trigger(
                name=stage,
                trigger={
                    "include": [
                        {
                            "artifact": pipeline_file,
                            "job": collect_job.name,
                        }
                    ],
                    "strategy": "depend",
                },
                needs=needs,
                stage=stage,
            )
            build_workflow.add_trigger(trigger)
            write_yaml(stage_pipeline, pipeline_file)

    write_yaml(build_workflow.to_dict(), "spack_pipeline.yaml")


def generate_containers_workflow(existing_workflow, architectures):
    """
    Generate the jobs to build the spackah containers
    """
    builder = Spacktainerizer(name="builder", build_path="builder")

    workflow = Workflow()
    for architecture in architectures:
        arch_job = Job(
            "generate spackah jobs",
            force_needs=True,
            **copy.deepcopy(generate_containers_workflow_yaml),
            architecture=architecture,
        )
        arch_job.image = {"name": f"{builder.registry_image}:{builder.registry_image_tag}",
                          "pull_policy": "always"}
        arch_job.needs.extend(
            [j.name for j in get_arch_or_multiarch_job(existing_workflow, architecture)]
        )
        arch_job.variables["ARCHITECTURE"] = architecture
        arch_job.variables["OUTPUT_DIR"] = f"artifacts.{architecture}"

        workflow.add_job(arch_job)
    return workflow


def generate_clean_cache_workflow(architectures):
    """
    Generate the jobs to clean the build cache
    """
    workflow = Workflow()
    stage = "clean build cache"
    workflow.stages = [stage]
    for architecture in architectures:
        arch_job = Job(
            "clean build cache",
            architecture=architecture,
            stage=stage,
            **copy.deepcopy(clean_cache_yaml),
        )

        bucket_info = architecture_map[architecture]["cache_bucket"]
        arch_job.needs = [
            {
                "job": f"generate build cache population job for {architecture}",
                "artifacts": True,
            }
        ]
        arch_job.variables = {
            "SPACK_ENV": f"jobs_scratch_dir.{architecture}/concrete_environment/spack.lock",
            "BUCKET": bucket_info["name"],
            "MAX_AGE": bucket_info["max_age"],
        }
        workflow.add_job(arch_job)

    return workflow


@jc.command
@click.option(
    "--singularity-version", "-S", default="4.0.2", help="Singularity version"
)
@click.option("--s3cmd-version", "-s", default="2.3.0", help="s3cmd version")
@click.option(
    "--output-file",
    "-o",
    default="generated_pipeline.yaml",
    help="Which file to write the output to",
)
def create_jobs(singularity_version, s3cmd_version, output_file):
    architectures = get_architectures()
    workflow = generate_base_container_workflow(
        singularity_version, s3cmd_version, architectures=architectures
    )
    workflow += generate_packages_workflow(architectures)
    workflow += generate_clean_cache_workflow(architectures)
    workflow += generate_containers_workflow(workflow, architectures)

    for job in [
        j
        for j in workflow.jobs
        if "generate build cache population" in j.name or "generate spackah" in j.name
    ]:
        logger.debug(f"Adding needs for {job.name}")
        [
            job.add_need(need.name)
            for need in get_arch_or_multiarch_job(workflow, job.architecture)
        ]

    # TODO
    # * rules?
    write_yaml(workflow.to_dict(), output_file)


if __name__ == "__main__":
    jc()
