# Bare OS image to run the installed executables
ARG BASE_IMAGE=ubuntu:24.04
FROM $BASE_IMAGE

ONBUILD RUN apt-get update \
         && apt-get install -y libatomic1 libgfortran5 libgomp1 binutils \
         && rm -rf /var/lib/apt/lists/*

ONBUILD COPY --from=builder /opt/spack-environment /opt/spack-environment
ONBUILD COPY --from=builder /opt/software /opt/software
ONBUILD COPY --from=builder /opt/._view /opt/._view
ONBUILD COPY --from=builder /opt/view /opt/view
ONBUILD COPY --from=builder /etc/profile.d/z10_spack_environment.sh /etc/profile.d/z10_spack_environment.sh
ONBUILD RUN echo "/opt/view/lib" > /etc/ld.so.conf.d/custom.conf && ldconfig -f /etc/ld.so.conf.d/custom.conf

ONBUILD ENTRYPOINT ["/bin/bash", "--rcfile", "/etc/profile", "-l", "-c", "$*", "--" ]
ONBUILD CMD [ "/bin/bash" ]
