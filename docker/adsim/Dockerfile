# The synApps image contains EPICS Base, ADCore R3-11, simDetector and HDF5 support.
FROM prjemian/synapps@sha256:1f0696e4262e50855197be1c73c2d7d16b645684e97814faad200c8d4008cc73
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG ADZMQ_COMMIT=6c5334fd54830d93bc76cb3d8760c97001aa3024

# Pin the Debian release used by the base image rather than following stable.
RUN sed -i '/debian-security/d; s/stable/bullseye/g; s|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libzmq3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/synApps/support/areaDetector-R3-11/ADZMQ \
    && curl --fail --location --retry 3 \
       "https://codeload.github.com/paulscherrerinstitute/ADZMQ/tar.gz/${ADZMQ_COMMIT}" \
       | tar -xz --strip-components=1 -C /opt/synApps/support/areaDetector-R3-11/ADZMQ

# Link Debian's ZeroMQ rather than the bundled prebuilt library.
RUN cd /opt/synApps/support/areaDetector-R3-11/ADZMQ \
    && sed -i '/^LIB_INSTALLS_Linux/d' zmqApp/zmqSrc/Makefile \
    && sed -i 's/ADZMQ_LIBS += $(LIBZMQ) NDPlugin/ADZMQ_LIBS += NDPlugin\nADZMQ_SYS_LIBS += zmq/' zmqApp/src/Makefile \
    && sed -i 's/$(PROD_NAME)_LIBS += ADZMQ $(LIBZMQ)/$(PROD_NAME)_LIBS += ADZMQ\n$(PROD_NAME)_SYS_LIBS += zmq/' iocs/zmqIOC/zmqApp/src/Makefile \
    && cp /usr/include/zmq.h /usr/include/zmq_utils.h zmqApp/zmqSrc/ \
    && make -j2
RUN printf '\nADZMQ=/opt/synApps/support/areaDetector-R3-11/ADZMQ\n' >> /opt/synApps/support/areaDetector-R3-11/ADSimDetector/iocs/simDetectorIOC/configure/RELEASE.local \
    && sed -i '/include $(ADCORE)\/ADApp\/commonDriverMakefile/i $(PROD_NAME)_DBD += ADZMQSupport.dbd\nPROD_LIBS += ADZMQ\nPROD_SYS_LIBS += zmq' /opt/synApps/support/areaDetector-R3-11/ADSimDetector/iocs/simDetectorIOC/simDetectorApp/src/Makefile \
    && cd /opt/synApps/support/areaDetector-R3-11/ADSimDetector/iocs/simDetectorIOC \
    && make -j2

COPY start-ioc.sh /usr/local/bin/start-adsim-ioc
COPY st.cmd /config/st.cmd
RUN chmod +x /usr/local/bin/start-adsim-ioc && mkdir -p /data
ENV PATH="/opt/base/bin/linux-x86_64:${PATH}" \
    EPICS_CA_SERVER_PORT=6064 \
    EPICS_CA_REPEATER_PORT=6065 \
    EPICS_CA_MAX_ARRAY_BYTES=10000000
WORKDIR /opt/synApps/support/areaDetector-R3-11/ADSimDetector/iocs/simDetectorIOC/iocBoot/iocSimDetector
EXPOSE 6064/tcp 6064/udp 5555/tcp
HEALTHCHECK --interval=5s --timeout=4s --start-period=15s --retries=6 \
    CMD EPICS_CA_AUTO_ADDR_LIST=NO EPICS_CA_ADDR_LIST="127.0.0.1:${EPICS_CA_SERVER_PORT}" caget -w 2 BEC:SIM:cam1:PortName_RBV >/dev/null || exit 1
ENTRYPOINT ["/usr/local/bin/start-adsim-ioc"]
CMD ["/opt/synApps/support/areaDetector-R3-11/ADSimDetector/iocs/simDetectorIOC/bin/linux-x86_64/simDetectorApp", "/config/st.cmd"]
