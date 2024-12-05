# Spacktainers


## Containers Built With Spack Packages

After having deployed our software on BB5 as modules for a long time, the move to the cloud calls for a different way of deploying software: containers. They offer more flexibility and will tie us less strongly to any specific cloud provider.

This repository aims to be the one-stop shop for all of our container needs.

## Defining containers

The only files you should have to edit as an end-user are located in the `container_definitions` folder. There's a subfolder per architecture (currently supported: `amd64` and `arm64`) under which both `spack.yaml` (in subdirectories) and `def` files can live.
* A `spack.yaml` file file defines a Spack container - in it you can define the Spack specs as you would in a Spack environment. If you have specific requirements for dependencies, you can add `spack: packages: ...` keys to define those, again, as in a Spack environment.
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
```

# Developer documentation

## Build Order

1. base containers
   * Build runtime / builder
2. application containers
   * Build containers
     * Every package build will be pushed to the cash directly after build
   * Publish containers

## CI/CD Variables

* `AWS_CACHE_ACCESS_KEY_ID` / `AWS_CACHE_SECRET_ACCESS_KEY`: AWS keypair for accessing the cache bucket hosted by Amazon
* `AWS_INFRASTRUCTURE_ACCESS_KEY_ID` / `AWS_INFRASTRUCTURE_SECRET_ACCESS_KEY`: AWS keypair for accessing the containers bucket hosted by Amazon (bbpinfrastructureassets)
* `SPACK_DEPLOYMENT_KEY_PRIVATE`: the Spack private deployment key (as a file!)
* `SPACK_DEPLOYMENT_KEY_PUBLIC`: the Spack public deployment key (as a file!)
* `GHCR_USER` / `GHCR_TOKEN`: the user and associated access token to write to the GitHub Container Registry (GHCR)
* `GITLAB_API_TOKEN`: private (!) gitlab token with API_READ access (CI_JOB_TOKEN does not have enough permissions). Change this once I'm gone

## Repository layout

Folders of note are:

* builder: base container that contains our spack fork, needed to build the software that will be in the spacktainer
* container_definitions: this is where users will define their containers
* runtime: base container that contains everything needed to run the spack-built environment

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

## Pulling images with Apptainer, Podman, or Sarus

Make sure you have your AWS credentials set up.  Then identify the image you want to run.
In the following, `spacktainers/neurodamus-neocortex` is going to be used.  Identify the
URL of the registry:
```
❯ aws ecr describe-repositories --repository-names spacktainers/neurodamus-neocortex
{
    "repositories": [
        {
            "repositoryArn": "arn:aws:ecr:us-east-1:130659266700:repository/spacktainers/neurodamus-neocortex",
            "registryId": "130659266700",
            "repositoryName": "spacktainers/neurodamus-neocortex",
            "repositoryUri": "130659266700.dkr.ecr.us-east-1.amazonaws.com/spacktainers/neurodamus-neocortex",
            "createdAt": "2024-11-20T17:32:11.169000+01:00",
            "imageTagMutability": "MUTABLE",
            "imageScanningConfiguration": {
                "scanOnPush": false
            },
            "encryptionConfiguration": {
                "encryptionType": "AES256"
            }
        }
    ]
}

```
Note the `repositoryUri` key. This will be used to log in with either Podman or Sarus.

Get a login token from AWS:
```
❯ aws ecr get-login-password
[secret]
```

### Pulling with Apptainer (or Singularity)

Pull from the registry, logging in at the same time with the `AWS` username and token from
above:
```
❯ apptainer pull --docker-login docker://130659266700.dkr.ecr.us-east-1.amazonaws.com/spacktainers/neurodamus-neocortex
```
The resulting `neurodamus-neocortex.sif` file is the container and can be copied to a
better storage location as desired.

### Pulling with Podman

Log into the registry, using `AWS` as the username:
```
❯ aws ecr get-login-password|podman login -u AWS --password-stdin 130659266700.dkr.ecr.us-east-1.amazonaws.com
```
Then pull the full `repositoryUri`:
```
❯ podman pull 130659266700.dkr.ecr.us-east-1.amazonaws.com/spacktainers/neurodamus-neocortex
```

### Pulling with Sarus

Everything in Sarus goes into one command:
```
❯ sarus pull --login -u AWS 130659266700.dkr.ecr.us-east-1.amazonaws.com/spacktainers/neurodamus-neocortex
```

## Reproducing GitHub Action builds containerized

First the `builder` and `runtime` containers need to be built locally, with corresponding tags:
```
❯ podman build --format=docker builder -t local_builder
❯ podman build --format=docker runtime -t local_runtime
```

Then create a new directory and add a `Dockerfile` inside, with the following contents:
```
FROM local_builder AS builder
FROM local_runtime AS runtime

COPY --from=builder /etc/debian_version /etc/debian_version
```
The last line is sometimes required to avoid optimizations that would skip including the
`builder` container.

Use a local Spack installation to create a GPG keypair to sign built packages, i.e:
```
❯ spack gpg create --export-secret key --export key.pub "Le Loup" "le.loup@epfl.ch"
```

And create a `spack.yaml`, i.e.:
```
spack:
  specs:
    - zlib
  packages:
    all:
      providers:
        mpi: [mpich]
```
The provider setting to prefer `mpich` may be helpful to execute the containers later with
a runtime and SLURM using `srun --mpi=pmi2 ...`, which will facilitate better MPI
communications.

Then build the Docker file:
```
❯ podman build --format=docker .
```

### Using the official builder

See above instructions under [pulling containers](#user-content-pulling-with-podman) to
login and pull the `spacktainers/builder` container.
Then launch the container and install something, i.e., with:
```
❯ podman pull ghcr.io/bluebrain/spack-builder:latest
❯ podman run -it ghcr.io/bluebrain/spack-builder:latest
root@43dec0527c62:/# (cd /opt/spack-repos/ && git pull)
Already up to date.
root@43dec0527c62:/# spack install zlib
[...]
```
Environments may be recreated as present under
[`container_definitions/`][(./container_definitions).

You may use a `Dockerfile` as constructed above, but replace the local tags with the
GitHub container registry ones to build a `spack.yaml`, too:
```
FROM ghcr.io/bluebrain/spack-builder AS builder
FROM ghcr.io/bluebrain/spack-runtime AS runtime

COPY --from=builder /etc/debian_version /etc/debian_version
```
This will still require a local GPG key pair to sign packages!

## Reproducing GitHub Action builds locally (outside a container)

Prerequisites needed to try the container building locally:

0. A installation using Ubuntu 24.04 LTS, with compilers set up
1. The upstream Spack commit we are using in the
   [`builder/Dockerfile`](builder/Dockerfile), in the argument `SPACK_BRANCH` (may be
   overwritten by the CI).  Referred to as `${SPACK_BRANCH}` here.
2. Access to the S3 bucket that holds the binary cache, denoted by the `CACHE_BUCKET`
   argument in the same file.  Referred to as `${CACHE_BUCKET}` here.

Set up upstream Spack, and source it:
```
❯ gh repo clone spack/spack
❯ cd spack
❯ git fetch --depth=1 origin ${SPACK_BRANCH}
❯ git reset --hard FETCH_HEAD
❯ . ./share/spack/setup-env.sh
❯ cd ..
```
Then clone our own Spack fork and add the repositories:
```
❯ gh repo clone BlueBrain/spack spack-blue
❯ spack repo add --scope=site spack-blue/bluebrain/repo-patches
❯ spack repo add --scope=site spack-blue/bluebrain/repo-bluebrain
```
Configure the mirror and set the generic architecture:
```
❯ spack mirror add --scope=site build_s3 ${CACHE_BUCKET}
❯ spack config --scope=site add packages:all:require:target=x86_64_v3
```
Now the basic Spack installation should be ready to use and pull from the build cache.

Then one may pick a container specification and create environments from it, i.e.:
```
❯ spack env create brindex spacktainers/container_definitions/amd64/py-brain-indexer/spack.yaml
❯ spack env activate brindex
❯ spack concretize -f
❯ spack install
```

# Acknowledgment

The development of this software was supported by funding to the Blue Brain Project,
a research center of the École polytechnique fédérale de Lausanne (EPFL),
from the Swiss government's ETH Board of the Swiss Federal Institutes of Technology.

Copyright (c) 2023-2024 Blue Brain Project/EPFL

