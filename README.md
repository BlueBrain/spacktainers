# Spacktainers


## Containers Built With Spack Packages

After having deployed our software on BB5 as modules for a long time, the move to the cloud calls for a different way of deploying software: containers. They offer more flexibility and will tie us less strongly to any specific cloud provider.

This repository aims to be the one-stop shop for all of our container needs.

## Defining containers

The only files you should have to edit as an end-user are located in the `container_definitions` folder. There's a subfolder per architecture (currently supported: `amd64` and `arm64`) under which both `spack.yaml` (in subdirectories) and `def` files can live.
* A `spack.yaml` file file defines a Spack container - in it you can define the Spack specs as you would in a Spack environment. If you have specific requirements for dependencies, you can add `spack: packages: ...` keys to define those, again, as in a Spack environment.
* If a `Dockerfile.epilogue` is present in the container directory, it will be appended to
the auto-generated `Dockerfile`. This can be used to, e.g., include compilers in the final
container and perform other fine-tuning.
* A def file defines a singularity container that will be built from an existing container on docker-hub. nexus-storage is already defined for amd64 as an example.

In both cases, the filename will be used as the name of your container. In case of a YAML file, the container version will be derived from the first package in your spec. In case of a def file, the version will be the same as the tag on docker hub.

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

**Note that all images are also available from the GitHub Container Registry (GHCR), i.e.,
via `apptainer pull docker://ghcr.io/bluebrain/spack-neurodamus-neocortex`. The URL has to
be all lowercase, and the download will work without login.**

### Pulling with Apptainer (or Singularity)

Pull from the registry, logging in at the same time with the `AWS` username and token from
above:
```
❯ apptainer pull --docker-login docker://130659266700.dkr.ecr.us-east-1.amazonaws.com/spacktainers/neurodamus-neocortex
```
The resulting `neurodamus-neocortex.sif` file is the container and can be copied to a
better storage location as desired.

NB: `apptainer` and `singularity` may, in almost all circumstances, be treated
interchangeably.

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

## Running the containers

**To have the best results possible, it is imperative that when running on clusters,
`srun` is called with `srun --mpi=pmi2` to have the MPI in the container interface
properly with the MPI on the cluster.**

With all container runtime engines, directories that contain the data to be processed and
output directories have to be mounted inside the container.
The following two examples show how to do this on either CSCS or SCITAS.

Also note that the Python paths given in these examples may vary between containers.  It
is best to first run a container interactively and make sure that `init.py` is properly
located.

### Running with Sarus

The following is a submission file that shows how to run Neurodamus on Eiger at CSCS.
Note the invocation of Sarus with `sarus run --mpi` _as well as_ `srun --mpi=pmi2`.  This
also shows how to mount data directories:
```
#!/bin/bash
#SBATCH --account=g156
#SBATCH --partition=normal
#SBATCH --nodes=16
#SBATCH --tasks-per-node=128
#SBATCH --exclusive
##SBATCH --mem=0
#SBATCH --constraint=mc
#SBATCH --time=04:00:00

WORKDIR=/project/g156/magkanar/ticket
DATADIR=/project/g156/NSETM-1948-extract-hex-O1/O1_data_physiology/
IMAGE=130659266700.dkr.ecr.us-east-1.amazonaws.com/spacktainers/neurodamus-neocortex

srun --mpi=pmi2 \
	sarus run --mpi \
			--env=HDF5_USE_FILE_LOCKING=FALSE \
			--workdir=${PWD} \
			--mount=type=bind,source=${DATADIR},destination=${DATADIR} \
			--mount=type=bind,source=${PWD},destination=${PWD} \
		${IMAGE} \
		special -mpi -python /opt/view/lib/python3.13/site-packages/neurodamus/data/init.py --configFile=${PWD}/simulation_config_O1_full.json --enable-shm=OFF --coreneuron-direct-mode
```

### Running with Apptainer

The following is a submission file that shows how to run Neurodamus on Jed from SCITAS.
Note that the `/work` directory with data was mounted with `-B /work/lnmc`:
```
#!/bin/zsh
#
#SBATCH --nodes 2
#SBATCH --qos parallel
#SBATCH --tasks-per-node 72
#SBATCH --time 2:00:0

CONFIG=/work/lnmc/barrel_cortex/mouse-simulations/simulation_config.json
OUTPUT=/work/lnmc/matthias_test_delete_me_please/apptainah

srun --mpi=pmi2 \
	apptainer run -B /work/lnmc/ -B ${HOME} /work/lnmc/software/containers/spack-neurodamus-neocortex_latest.sif \
		special \
		-mpi \
		-python \
		/opt/view/lib/python3.13/site-packages/neurodamus/data/init.py \
		--configFile=${HOME}/simulation_config.json \
		--enable-shm=OFF \
		--coreneuron-direct-mode \
		--output-path=${OUTPUT} \
		--lb-mode=WholeCell
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

### Converting images to Singularity SIF locally

To convert images to Singularity locally, it seems simplest to first start a local
Docker registry:
```
❯ podman container run -dt -p 5000:5000 --name registry docker.io/library/registry:2
```

Then build, tag, and upload a Dockerfile to the registry:
```
❯ podman build -v $PWD:/src . -t localhost:5000/td
❯ podman push localhost:5000/td
```
The image from the registry can now be converted:
```
❯ SINGULARITY_NOHTTPS=1 singularity pull docker://localhost:5000/td:latest
```

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

