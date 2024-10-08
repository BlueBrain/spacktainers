parent_pipeline_rule = {
    "rules": [
        {"if": "$CI_PIPELINE_SOURCE == 'parent_pipeline'"},
    ]
}

buildah_include_yaml = {
    "include": [
        {"project": "cs/gitlabci-templates", "file": "/build-image-using-buildah.yml"}
    ],
}

bbp_containerizer_include_yaml = {
    "include": [
        {
            "project": "nse/bbp-containerizer",
            "file": "/python/ci/templates/convert-image.yml",
        }
    ],
}

buildah_build_yaml = {
    "extends": ".build-image-using-buildah",
    "stage": "build base containers",
    "timeout": "8h",
    "variables": {
        "KUBERNETES_CPU_LIMIT": 4,
        "KUBERNETES_CPU_REQUEST": 2,
        "KUBERNETES_MEMORY_LIMIT": "16Gi",
        "KUBERNETES_MEMORY_REQUEST": "4Gi",
        "REGISTRY_IMAGE_TAG": "",
        "BUILD_PATH": "",
        "CI_REGISTRY_IMAGE": "",
        "BUILDAH_EXTRA_ARGS": (
            '--label org.opencontainers.image.revision="$CI_COMMIT_SHA"'
            ' --label org.opencontainers.image.authors="$GITLAB_USER_NAME <$GITLAB_USER_EMAIL>"'
            ' --label org.opencontainers.image.url="$CI_PROJECT_URL"'
            ' --label org.opencontainers.image.source="$CI_PROJECT_URL"'
            ' --label org.opencontainers.image.created="$CI_JOB_STARTED_AT"'
            ' --label ch.epfl.bbpgitlab.ci-pipeline-url="$CI_PIPELINE_URL"'
            ' --label ch.epfl.bbpgitlab.ci-commit-branch="$CI_COMMIT_REF_SLUG" '
        ),
    },
    **parent_pipeline_rule,
}

multiarch_yaml = {
    "image": "ubuntu:22.04",
    "stage": "base containers multiarch",
    "script": [
        "apt-get update && apt-get install -y podman",
        'echo "Creating multiarch manifest %REGISTRY_IMAGE%:%REGISTRY_IMAGE_TAG%"',
        "podman login -u ${CI_REGISTRY_USER} -p ${CI_REGISTRY_PASSWORD} --tls-verify=false ${CI_REGISTRY}",
        "podman manifest create mylist",
        'echo "Adding %REGISTRY_IMAGE%:%REGISTRY_IMAGE_TAG%-arm64"',
        "podman manifest add --tls-verify=false mylist %REGISTRY_IMAGE%:%REGISTRY_IMAGE_TAG%-arm64",
        'echo "Adding %REGISTRY_IMAGE%:%REGISTRY_IMAGE_TAG%-amd64"',
        "podman manifest add --tls-verify=false mylist %REGISTRY_IMAGE%:%REGISTRY_IMAGE_TAG%-amd64",
        "podman manifest push --tls-verify=false mylist %REGISTRY_IMAGE%:%REGISTRY_IMAGE_TAG%",
        'if [[ "$CI_COMMIT_REF_SLUG" == "$CI_DEFAULT_BRANCH" ]]; then',
        '    echo "Also creating multiarch manifest for %REGISTRY_IMAGE%:latest multiarch"',
        "    podman manifest create mylist-latest",
        '    echo "Adding %REGISTRY_IMAGE%:latest-arm64"',
        "    podman manifest add --tls-verify=false mylist-latest %REGISTRY_IMAGE%:latest-arm64",
        '    echo "Adding %REGISTRY_IMAGE%:latest-amd64"',
        "    podman manifest add --tls-verify=false mylist-latest %REGISTRY_IMAGE%:latest-amd64",
        "    podman manifest push --tls-verify=false mylist-latest %REGISTRY_IMAGE%:latest",
        "fi",
    ],
    **parent_pipeline_rule,
}

packages_yaml = {
    "timeout": "1h",
    "stage": "generate build cache population job",
    "script": [
        "cat /proc/cpuinfo",
        "cat /proc/meminfo",
        'git config --global url."https://gitlab-ci-token:${CI_JOB_TOKEN}@bbpgitlab.epfl.ch/".insteadOf ssh://git@bbpgitlab.epfl.ch/',
        ". $SPACK_ROOT/share/spack/setup-env.sh",
        "spack arch",
        'spack gpg trust "$SPACK_DEPLOYMENT_KEY_PUBLIC"',
        'spack gpg trust "$SPACK_DEPLOYMENT_KEY_PRIVATE"',
        "cat spack.yaml",
        "spack env activate --without-view .",
        "spack config blame packages",
        "spack config blame mirrors",
        "spack compiler find",
        "spack concretize -f",
        'spack -d ci generate --check-index-only --artifacts-root "${ENV_DIR}" --output-file "${ENV_DIR}/${CI_JOB_NAME}.yml"',
    ],
    "artifacts": {"when": "always", "paths": ["${ENV_DIR}"]},
    **parent_pipeline_rule,
}

process_spack_pipeline_yaml = {
    "image": "ubuntu:22.04",
    "stage": "process spack-generated pipelines",
    "script": [
        "apt-get update && apt-get install -y ca-certificates git python3 python3-pip",
        "pip install --upgrade pip setuptools",
        "pip install -e ./job_creator",
        "find ${SPACK_PIPELINES_ARCH_DIR}",
        "jc process-spack-pipeline -d ${SPACK_PIPELINES_ARCH_DIR} -o ${OUTPUT_DIR}",
    ],
    "artifacts": {
        "when": "always",
        "paths": ["artifacts.*", "*spack_pipeline.yaml", "job_creator.log"],
    },
    **parent_pipeline_rule,
}

clean_cache_yaml = {
    "image": "python:3.10-buster",
    "timeout": "4h",
    "allow_failure": True,
    "script": [
        "apt-get update && apt-get install -y git",
        "pip install ./spackitor",
        "git clone https://github.com/bluebrain/spack",
        "spackitor ${SPACK_ENV_ARGS} --bucket ${BUCKET} --max-age ${MAX_AGE} --spack-directory ./spack",
    ],
    **parent_pipeline_rule,
}

generate_containers_workflow_yaml = {
    "stage": "generate containers workflow",
    "variables": {
        "KUBERNETES_CPU_LIMIT": 4,
        "KUBERNETES_CPU_REQUEST": 2,
        "KUBERNETES_MEMORY_LIMIT": "16Gi",
        "KUBERNETES_MEMORY_REQUEST": "4Gi",
    },
    "script": [
        "apt-get update && apt-get install -y ca-certificates git python3 python3-pip skopeo",
        "pip install --upgrade pip setuptools",
        "pip install -e ./job_creator",
        "jc generate-spacktainer-workflow -a ${ARCHITECTURE} -o ${OUTPUT_DIR} -s ${S3CMD_VERSION}",
    ],
    "artifacts": {
        "when": "always",
        "paths": [
            "artifacts.*/*/*/spack.lock",
            "artifacts.*/*/*/spack.yaml",
            "${OUTPUT_DIR}",
            "job_creator.log",
        ],
    },
    **parent_pipeline_rule,
}

build_spacktainer_yaml = {
    "stage": "build spacktainer containers",
    "extends": ".build-image-using-buildah",
    "variables": {
        "KUBERNETES_CPU_LIMIT": 4,
        "KUBERNETES_CPU_REQUEST": 2,
        "KUBERNETES_MEMORY_LIMIT": "16Gi",
        "KUBERNETES_MEMORY_REQUEST": "4Gi",
        "BUILDAH_EXTRA_ARGS": (
            ' --label org.opencontainers.image.revision="$CI_COMMIT_SHA"'
            ' --label org.opencontainers.image.authors="$GITLAB_USER_NAME <$GITLAB_USER_EMAIL>"'
            ' --label org.opencontainers.image.url="$CI_PROJECT_URL"'
            ' --label org.opencontainers.image.source="$CI_PROJECT_URL"'
            ' --label org.opencontainers.image.created="$CI_JOB_STARTED_AT"'
            ' --label ch.epfl.bbpgitlab.ci-pipeline-url="$CI_PIPELINE_URL"'
            ' --label ch.epfl.bbpgitlab.ci-commit-branch="$CI_COMMIT_REF_SLUG"'
            ' --build-arg GITLAB_CI="$GITLAB_CI"'
            ' --build-arg CI_JOB_TOKEN="$CI_JOB_TOKEN"'
        ),
    },
    "before_script": [
        "mkdir -p ${BUILD_PATH}",
        "cp $SPACK_ENV_DIR/spack.yaml ${BUILD_PATH}/",
    ],
    **parent_pipeline_rule,
}

create_sif_yaml = {
    "stage": "create SIF files",
    "variables": {
        "KUBERNETES_CPU_LIMIT": 4,
        "KUBERNETES_CPU_REQUEST": 2,
        "KUBERNETES_MEMORY_LIMIT": "16Gi",
        "KUBERNETES_MEMORY_REQUEST": "4Gi",
    },
    "script": [
        "/bin/bash",
        "cat /root/.s3cfg",
        "ps",
        "export SINGULARITY_DOCKER_USERNAME=${CI_REGISTRY_USER}",
        "export SINGULARITY_DOCKER_PASSWORD=${CI_JOB_TOKEN}",
        'singularity pull --no-https "${FS_CONTAINER_PATH}" "docker://${CI_REGISTRY_IMAGE}:${REGISTRY_IMAGE_TAG}"',
        "set +e",
        "container_info=$(s3cmd info ${S3_CONTAINER_PATH}); retval=$?",
        "echo $retval",
        "set -e",
        "if [[ ${retval} -ne 0 ]]; then",
        "    echo ${S3_CONTAINER_PATH} does not exist yet - deleting old versions and uploading",
        "    for existing_sif in $(s3cmd ls s3://${BUCKET}/containers/${CONTAINER_NAME}__ | awk '{print $4}'); do",
        "        LAST_MOD=$(s3cmd info ${existing_sif} | awk '/^\s+Last mod:/' | tr -d ':')",
        "        echo last mod is ${LAST_MOD}",
        "        remove=$(python -c \"from datetime import datetime, timedelta; print(datetime.strptime('${LAST_MOD}'.strip(), 'Last mod  %a, %d %b %Y %H%M%S %Z') < datetime.now() - timedelta(weeks=1))\")",
        "        echo remove is ${remove}",
        '        if [ "${remove}" == "True" ]; then',
        "            echo Removing ${existing_sif}",
        "            s3cmd rm ${existing_sif}",
        "        else",
        "            echo ${existing_sif} is less than a week old - keeping it for now as it might still be in use.",
        "        fi" "    done",
        "    echo Uploading",
        "    s3cmd put --add-header x-amz-meta-container-checksum:${CONTAINER_CHECKSUM} --add-header x-amz-meta-spack-lock-sha256:${SPACK_LOCK_SHA256} ${FS_CONTAINER_PATH} ${S3_CONTAINER_PATH}",
        "else",
        "    echo ${S3_CONTAINER_PATH} exists - checking sha256sum",
        "    bucket_spack_lock_sha256=$(echo ${container_info} | awk -F':' '/x-amz-meta-spack-lock-sha256/ {print $2}' | sed 's/ //g')",
        "    bucket_container_checksum=$(echo ${container_info} | awk -F':' '/x-amz-meta-container-checksum/ {print $2}' | sed 's/ //g')",
        '    echo "Bucket spack lock sha256 is ${bucket_spack_lock_sha256} (expected ${SPACK_LOCK_SHA256})"',
        '    echo "Bucket container checksum is ${bucket_container_checksum} (expected ${CONTAINER_CHECKSUM})"',
        '    if [[ "${CONTAINER_CHECKSUM}" != "${bucket_container_checksum}" ]] || [[ "${SPACK_LOCK_SHA256}" != "${bucket_spack_lock_sha256}" ]]; then',
        "        echo checksum mismatch - re-uploading",
        "        s3cmd put --add-header x-amz-meta-container-checksum:${CONTAINER_CHECKSUM} --add-header x-amz-meta-spack-lock-sha256:${SPACK_LOCK_SHA256} ${FS_CONTAINER_PATH} ${S3_CONTAINER_PATH}",
        "    else",
        "        echo checksums match - nothing to do here",
        "    fi",
        "fi",
    ],
    **parent_pipeline_rule,
}

build_custom_containers_yaml = {
    "stage": "create SIF files",
    "variables": {
        "KUBERNETES_CPU_LIMIT": 4,
        "KUBERNETES_CPU_REQUEST": 2,
        "KUBERNETES_MEMORY_LIMIT": "16Gi",
        "KUBERNETES_MEMORY_REQUEST": "4Gi",
    },
    "script": [
        "cat /root/.s3cfg",
        "echo Building SIF",
        "singularity build ${CONTAINER_FILENAME} ${CONTAINER_DEFINITION}",
        "echo Uploading ${CONTAINER_FILENAME} to ${S3_CONTAINER_PATH}",
        "s3cmd put --add-header x-amz-meta-digest:${SOURCE_DIGEST} ${CONTAINER_FILENAME} ${S3_CONTAINER_PATH}",
    ],
    **parent_pipeline_rule,
}

docker_hub_push_yaml = {
    "stage": "push to docker hub",
    "image": "ubuntu:22.04",
    "variables": {
        "timeout": "4h",
    },
    "script": [
        "apt-get update",
        "apt-get install -y ca-certificates podman",
        "podman login -u ${CI_REGISTRY_USER} -p ${CI_REGISTRY_PASSWORD} --tls-verify=false ${CI_REGISTRY}",
        "podman login -u ${DOCKERHUB_USER} -p ${DOCKERHUB_PASSWORD} --tls-verify=false docker.io",
        "podman pull ${CI_REGISTRY_IMAGE}/${CONTAINER_NAME}:${REGISTRY_IMAGE_TAG}",
        "echo podman push ${CONTAINER_NAME}:${REGISTRY_IMAGE_TAG} docker://docker.io/bluebrain/${HUB_REPO_NAME}:${REGISTRY_IMAGE_TAG}",
        "podman image list",
        "echo Pushing, possibly twice because podman sometimes fails on the first attempt",
        "podman push ${CONTAINER_NAME}:${REGISTRY_IMAGE_TAG} docker://docker.io/bluebrain/${HUB_REPO_NAME}:${REGISTRY_IMAGE_TAG} || podman --log-level=debug push ${CONTAINER_NAME}:${REGISTRY_IMAGE_TAG} docker://docker.io/bluebrain/${HUB_REPO_NAME}:${REGISTRY_IMAGE_TAG}",
    ],
    **parent_pipeline_rule,
}

bb5_download_sif_yaml = {
    "stage": "download SIF to bb5",
    "tags": ["bb5_map"],
    "script": [
        "module load unstable singularityce",
        "if [ -e ${FULL_SIF_PATH} ]; then",
        "  EXISTING_SPACK_LOCK_CHECKSUM=$(singularity inspect ${FULL_SIF_PATH} | awk '/spack_lock_sha256/ {print $2}')",
        "  EXISTING_CONTAINER_CHECKSUM=$(singularity inspect ${FULL_SIF_PATH} | awk '/container_checksum/ {print $2}')",
        "  if [[ ${SPACK_LOCK_CHECKSUM} == ${EXISTING_SPACK_LOCK_CHECKSUM} ]] && [[ ${CONTAINER_CHECKSUM} == ${EXISTING_CONTAINER_CHECKSUM} ]]; then",
        "    echo ${FULL_SIF_PATH} 'exists and checksums match, nothing to do here'",
        "    exit 0",
        "  else",
        "    echo ${FULL_SIF_PATH} 'exists but checksums mismatch, re-downloading'",
        "    echo ${EXISTING_SPACK_LOCK_CHECKSUM} vs ${SPACK_LOCK_CHECKSUM}",
        "    echo ${EXISTING_CONTAINER_CHECKSUM} vs ${CONTAINER_CHECKSUM}",
        "    echo Removing ${FULL_SIF_PATH}",
        "    rm ${FULL_SIF_PATH}",
        "  fi",
        "fi",
        "echo Configuring s3cmd",
        "sed -i 's/^access_key.*/access_key='${AWS_INFRASTRUCTURE_ACCESS_KEY_ID}'/' _s3cfg",
        "sed -i 's/^secret_key.*/secret_key='${AWS_INFRASTRUCTURE_SECRET_ACCESS_KEY}'/' _s3cfg",
        "let length=$(($(echo $(expr index ${HTTP_PROXY:7} :)) - 1))",
        "PROXY_HOST=${HTTP_PROXY:7:${length}}",
        "PROXY_PORT=${HTTP_PROXY:$((7+${length}+1))}",
        "sed -i 's/^proxy_host.*/proxy_host='${PROXY_HOST}'/' _s3cfg",
        "sed -i 's/^proxy_port.*/proxy_port='${PROXY_PORT}'/' _s3cfg",
        "cat _s3cfg",
        "echo Downloading s3cmd",
        "wget https://github.com/s3tools/s3cmd/releases/download/v${S3CMD_VERSION}/s3cmd-${S3CMD_VERSION}.tar.gz",
        "tar xf s3cmd-${S3CMD_VERSION}.tar.gz",
        "export PATH=$(realpath ./s3cmd-${S3CMD_VERSION}):$PATH",
        "echo s3cmd get --config=_s3cfg s3://${BUCKET}/containers/${SIF_FILENAME} ${FULL_SIF_PATH}",
        "s3cmd get --config=_s3cfg s3://${BUCKET}/containers/${SIF_FILENAME} ${FULL_SIF_PATH}",
    ],
    **parent_pipeline_rule,
}
