# Spacktainers


## Containers Built With Spack Packages

After having deployed our software on BB5 as modules for a long time, the move to the cloud calls for a different way of deploying software: containers. They offer more flexibility and will tie us less strongly to any specific cloud provider.

This repository aims to be the one-stop shop for all of our container needs.

## Defining containers

The only files you should have to edit as an end-user are located in the `container_definitions` folder. There's a subfolder per architecture (currently supported: `amd64` and `arm64`) under which both `yaml` and `def` files can live.
* A YAML file file defines a Spack container - in it you can define the Spack specs as you would in a Spack environment. If you have specific requirements for dependencies, you can add `spack: packages: ...` keys to define those, again, as in a Spack environment.
* A def file defines a singularity container that will be built from an existing container on docker-hub. nexus-storage is already defined for amd64 as an example.

In both cases, the filename will be used as the name of your container. In case of a YAML file, the container version will be derived from the first package in your spec. In case of a def file, the version will be the same as the tag on docker hub.

## Adding extra files to your containers

Create a folder under `spacktainer/files` to hold your container's files. Make sure to use your container's name to keep everything somewhat orderly.
In your container definition file, add a `spacktainer` section with a `files` key. This key holds a list of `source:target` filepairs (note that there is no space between source and target!)
Source is specified starting from the level below `spacktainer`; in the example below the folder structure would look like this:

```
spacktainer/files
└── my-awesome-container
    ├── some_folder
    │   ├── brilliant_hack.patch
    │   ├── readme.txt
    │   ├── ugly_hack.patch
    │   └── useless_but_if_we_delete_it_everything_breaks.jpg
    └── script.sh

```

```
spack:
  specs:
    - my-awesome-package
spacktainer:
  files:
    - files/my-awesome-container/script.sh:/opt/script.sh
    - files/my-awesome-container/some_folder:/opt/some_folder
```

# Developer documentation

## Components

* Spacktainerizer: the base image which contains our spack fork
* Singularitah: arm64 container with singularity and s3cmd installation for sif manipulation on arm nodes
* Spack-cacher: builds spack packages and puts them in a build cache
* Spackitor: cleans the build cache: anything that is too old or no longer used gets removed
* Spackah: builds the actual containers

## Build Order

1. base containers
   * Build runtime / builder
   * Build singularitah
2. packages
   * Build cache
3. containers
   * Build containers
   * Publish containers

## Pipeline logic

While the pipeline is organised in stages, jobs jump the queue wherever they can to optimise build times. As such, we'll ignore the stages here and look at the actual execution order:
* `generate base pipeline`: the "entrypoint" that will generate the necessary jobs to:
    * build the builder, runtime and singularitah containers if necessary. These containers will be built only for the architectures needed for the final containers. These jobs will be generated only for the containers that need to be built.
    * run `spack ci generate` and process its output. This is needed because Gitlab imposes a fairly tight restriction on how large a YAML file can be and Spack can easily surpass that. To work around this, we take the output YAML and split it into multiple pipelines along the generated stages.
    * Clean the build cache buckets
* `base containers and pipeline generation`: will run the pipeline that was generated in the first step
* `gather child artifacts`: will collect the yaml generated in the `base containers and pipeline generation` child pipeline. This is needed because Gitlab doesn't allow triggering artifacts from a child pipeline
* `populate buildcache for amd64`: run the jobs that `spack ci generate` produced in order to populate the buildcache
* `build spacktainers for amd64`: this workflow was also generated in the `base containers and pipeline generation` child pipeline and will build the actual containers, if necessary.


## CI/CD Variables

* `AWS_CACHE_ACCESS_KEY_ID` / `AWS_CACHE_SECRET_ACCESS_KEY`: AWS keypair for accessing the cache bucket hosted by Amazon
* `AWS_INFRASTRUCTURE_ACCESS_KEY_ID` / `AWS_INFRASTRUCTURE_SECRET_ACCESS_KEY`: AWS keypair for accessing the containers bucket hosted by Amazon (bbpinfrastructureassets)
* `BBP_CACHE_ACCESS_KEY_ID` / `BBP_CACHE_SECRET_ACCESS_KEY`: AWS keypair for accessing the cache bucket hosted by BBP
* `SPACK_DEPLOYMENT_KEY_PRIVATE`: the Spack private deployment key (as a file!)
* `SPACK_DEPLOYMENT_KEY_PUBLIC`: the Spack public deployment key (as a file!)
* `DOCKERHUB_USER` / `DOCKERHUB_PASSWORD`: credentials for docker hub
* `GITLAB_API_TOKEN`: private (!) gitlab token with API_READ access (CI_JOB_TOKEN does not have enough permissions). Change this once I'm gone

## Base containers

* [Singularitah](bbpgitlab.epfl.ch:5050/hpc/spacktainers/singularitah)
* [Builder](bbpgitlab.epfl.ch:5050/hpc/spacktainers/builder)
* [Runner](bbpgitlab.epfl.ch:5050/hpc/spacktainers/runtime)

## Repository layout

There are a few python projects in this repository:

* get_artifacts: download artifacts from a pipeline. It's fairly specific to this repository.
* job_creator: the main project; this will take care of generating the jobs in this project. Both of the other ones are called at some point in the pipelines it generates. It is further detailed below.
* spackitor: the spack janitor that will clean the build cache. It has its own readme and comes with some useful scripts for manual actions.

Apart from that, folders of note are:

* builder: base container that contains our spack fork, needed to build the software that will be in the spacktainer
* container_definitions: this is where users will define their containers
* runtime: base container that contains everything needed to run the spack-built environment
* singularitah: base container that contains singularity and s3cmd
* spacktainer: contains the Dockerfile that will be used to build the spacky containers

## job_creator

The main entrypoints can be found, unsurprisingly, in the `__main__.py` file. This is where the `click` commands are defined.

`architectures.py` contains the configuration for different architectures: what bucket should be used for the Spack package cache, which tag should be applied for the gitlab jobs, in which variables is the authentication defined, etc

`ci_objects.py` contains helper object that can be used to define gitlab jobs and workflows. These will take care of architecture-specific behaviour (such as setting/unsetting the proxy, setting AWS variables, ...)

`containers.py` holds everything related to generating container jobs: classes that define the base containers (former Spacktainerizer, Singularitah) as well as the spacktainers (formerly Spackah) and custom containers. It also contains the methods that use these classes and return a workflow with only the required jobs.

`job_templates.py` holds job definition templates as python dictionaries.

`logging_config.py` should be self-explanatory

`packages.py` holds everything related to package-building jobs. Here you'll find the methods that generate the workflows for building the job that runs `spack ci generate` as well as the job that processes the output.

`spack_template.py` contains the spack.yaml template that will be merged with the user's container config to generate the spack.yaml that will be used to build the container

`utils.py` contains utility functions for reading/writing yaml, getting the multiarch job for a container, ...

# Acknowledgment

The development of this software was supported by funding to the Blue Brain Project,
a research center of the École polytechnique fédérale de Lausanne (EPFL),
from the Swiss government's ETH Board of the Swiss Federal Institutes of Technology.

Copyright (c) 2023-2024 Blue Brain Project/EPFL

