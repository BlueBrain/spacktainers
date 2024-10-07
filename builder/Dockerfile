ARG BASE_IMAGE=ubuntu:24.04
ARG MIRROR_URL=""
ARG CACHE_BUCKET="s3://spack-build-cache"
ARG SPACK_BRANCH="develop"
FROM $BASE_IMAGE as bootstrap

ENV SPACK_ROOT=/opt/spack \
    REPOS_ROOT=/opt/spack-repos \
    CURRENTLY_BUILDING_DOCKER_IMAGE=1 \
    DEBEAN_FRONTEND=noninteractive \
    container=docker

RUN apt-get update \
    && apt-get install -y build-essential curl environment-modules file gcc-12 g++-12 gfortran gfortran-12 git python3 python3-boto3 rpm unzip \
    && rm -rf /var/lib/apt/lists/*

# Yes, again. Line 1 by itself is not enough to export this ARG into the shell in RUN
ARG BASE_IMAGE
# BlueBrain internal S3 bucket
ARG MIRROR_URL
# For AWS S3 bucket
ARG CACHE_BUCKET
# Which branch to clone
ARG SPACK_BRANCH

SHELL ["/bin/bash", "--login", "-c"]

RUN echo "Cloning spack branch $SPACK_BRANCH"
RUN mkdir $SPACK_ROOT && cd $SPACK_ROOT \
    && git clone --depth=1 --single-branch --branch $SPACK_BRANCH https://github.com/spack/spack.git . \
    && mkdir -p $SPACK_ROOT/opt/spack

RUN ln -s $SPACK_ROOT/share/spack/docker/entrypoint.bash \
    /usr/local/bin/docker-shell \
    && ln -s $SPACK_ROOT/share/spack/docker/entrypoint.bash \
    /usr/local/bin/interactive-shell \
    && ln -s $SPACK_ROOT/share/spack/docker/entrypoint.bash \
    /usr/local/bin/spack-env

RUN mkdir $REPOS_ROOT && cd $REPOS_ROOT \
    && git clone --depth=1 --single-branch --branch $SPACK_BRANCH https://github.com/BlueBrain/spack.git .

RUN cp $SPACK_ROOT/share/spack/docker/modules.yaml \
    $SPACK_ROOT/etc/spack/modules.yaml \
    && cp $REPOS_ROOT/bluebrain/sysconfig/containers/packages.yaml \
    $REPOS_ROOT/etc/spack/packages.yaml \
    && rm -rf /root/*.* /run/nologin $SPACK_ROOT/.git

# [WORKAROUND]
# https://superuser.com/questions/1241548/
#     xubuntu-16-04-ttyname-failed-inappropriate-ioctl-for-device#1253889
RUN [ -f ~/.profile ]                                               \
    && sed -i 's/mesg n/( tty -s \\&\\& mesg n || true )/g' ~/.profile \
    || true

WORKDIR /root
SHELL ["docker-shell"]

# Add custom repositories: order matters, last one will be preferred
RUN spack repo add --scope=site $REPOS_ROOT/bluebrain/repo-patches
RUN spack repo add --scope=site $REPOS_ROOT/bluebrain/repo-bluebrain

# Creates the package cache
RUN spack compiler find --scope=site \
    && spack compiler list
# OpenGL cannot be build by Spack
RUN spack external find --scope=site opengl

# Possible ARM customizations (require Spack sourced)
# COPY acfl.sh acfl.sh
# RUN ./acfl.sh

# This will list any missing packages that should be installed via apt.
RUN spack bootstrap now
# Add the BBP build cache, this should only allow _read_ access.
RUN echo "Mirror URL is .${MIRROR_URL}. and CACHE_BUCKET is .${CACHE_BUCKET}."
RUN if [ -n "${MIRROR_URL}" ]; then spack mirror add --scope=site --s3-endpoint-url ${MIRROR_URL} bbpS3 ${CACHE_BUCKET}; fi

# COPY key.pub key.pub
# RUN spack gpg trust key.pub

# Build stage with Spack pre-installed and ready to be used
FROM bootstrap as builder

ENTRYPOINT ["/bin/bash", "/usr/local/bin/spack-env"]
# on graviton runners, the CMD does not seem to get appended to the ENTRYPOINT
#ENTRYPOINT ["/bin/bash", "/opt/spack/share/spack/docker/entrypoint.bash"]
#CMD ["interactive-shell"]

# What we want to install and how we want to install it
# is specified in a manifest file (spack.yaml)
RUN mkdir /opt/spack-environment
ONBUILD COPY spack.yaml /opt/spack-environment/spack.yaml

# May be needed for ARM compilers
ONBUILD RUN . /etc/profile.d/modules.sh

# Set the git token for CI builds
ONBUILD ARG CI_JOB_TOKEN
ONBUILD RUN if [[ -n "${CI_JOB_TOKEN}" ]]; then git config --global url."https://gitlab-ci-token:${CI_JOB_TOKEN}@bbpgitlab.epfl.ch/".insteadOf ssh://git@bbpgitlab.epfl.ch/ ; fi

# Set the git token for manual builds
ONBUILD ARG GITLAB_PRIVATE_TOKEN
ONBUILD RUN if [[ -n "${GITLAB_PRIVATE_TOKEN}" ]]; then git config --global url."https://oauth2:${GITLAB_PRIVATE_TOKEN}@bbpgitlab.epfl.ch/".insteadOf ssh://git@bbpgitlab.epfl.ch/ ; fi

ONBUILD RUN git config --list

ONBUILD ARG MIRROR_URL_ARG
ONBUILD ARG MIRROR_AUTH_ARG
ONBUILD ARG CACHE_BUCKET
ONBUILD RUN if [ -n "${CACHE_BUCKET}" ] ; then echo spack mirror add --scope=site ${MIRROR_URL_ARG} ${MIRROR_AUTH_ARG} build_s3 s3://${CACHE_BUCKET}; fi
ONBUILD RUN if [ -n "${CACHE_BUCKET}" ]; then spack mirror add --scope=site ${MIRROR_URL_ARG} ${MIRROR_AUTH_ARG} build_s3 s3://${CACHE_BUCKET}; fi
ONBUILD RUN ls /opt
ONBUILD RUN ls /opt/spack/bin
ONBUILD RUN echo $PATH
ONBUILD RUN spack config blame mirrors

# Install the software, remove unnecessary deps
ONBUILD RUN cd /opt/spack-environment && \
    spack env activate . && \
    spack concretize && \
    spack install --fail-fast && \
    spack gc -y

ONBUILD RUN if [ -n "${MIRROR_URL}" ]; then spack mirror rm build_s3; fi
# Strip all the binaries
ONBUILD RUN find -L /opt/view/* -type f -exec readlink -f '{}' \; | \
    xargs file -i | \
    grep 'charset=binary' | \
    grep 'x-executable\|x-archive\|x-sharedlib' | \
    awk -F: '{print $1}' | xargs strip -s

# Modifications to the environment that are necessary to run
ONBUILD RUN cd /opt/spack-environment && \
    spack env activate --sh -d . >> /etc/profile.d/z10_spack_environment.sh

# Singularity by default sets the LD_LIBRARY_PATH to /.singularity.d/libs that includes
# libraries mounted from the host system. Since spack when enabling the environment might
# overwrite the LD_LIBRARYT_PATH we make sure that /.singularity.d/libs is always there
ONBUILD RUN echo "if [[ \$LD_LIBRARY_PATH != *"/.singularity.d/libs"* ]]; then export LD_LIBRARY_PATH=\${LD_LIBRARY_PATH:+\$LD_LIBRARY_PATH:}/.singularity.d/libs; fi" >> /etc/profile.d/z10_spack_environment.sh
