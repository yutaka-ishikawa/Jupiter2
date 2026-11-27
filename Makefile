# Build outputs stay in build directories; the dev root persists in private
# user state. Install publishes already-built artifacts without compilation.
.DEFAULT_GOAL := build
.NOTPARALLEL:
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PREFIX ?= $(ROOT)/install/keystone
K3_BUILD_DIR ?= $(ROOT)/.build-k3
KEYSTONE_BUILD_DIR ?= $(ROOT)/.build-keystone
STAGE := $(abspath $(KEYSTONE_BUILD_DIR))/stage
JOBS ?= $(shell nproc)
KEYSTONE_SM_OPT_LEVEL ?= 2
CROSS_COMPILE ?= riscv64-linux-gnu-
OPTEE_CLIENT_OUT ?= $(ROOT)/.build-k3/optee-coexist/client/usr
ROOTFS_ARCHIVE ?=
ROOTFS_SHA256 ?=
export CROSS_COMPILE JOBS KEYSTONE_SM_OPT_LEVEL
K3_ARGS = --prefix "$(STAGE)" --build-dir "$(K3_BUILD_DIR)" --jobs "$(JOBS)"
SDK_ARGS = --build-dir "$(KEYSTONE_BUILD_DIR)" --jobs "$(JOBS)"
VERIFY_ARGS = KEYSTONE_BUILD_DIR="$(KEYSTONE_BUILD_DIR)" KERNEL_OUT="$(K3_BUILD_DIR)/linux"
COMPONENTS := qemu opensbi linux eyrie keystone rng crypto verifications samples
.PHONY: all build install build-install $(COMPONENTS) sm sdk firmware guest erie openSBI install-erie install-openSBI run help optee-coexist optee-coexist-test ftpm-ima $(addprefix install-,$(COMPONENTS))
all: build
build: $(COMPONENTS)
build-install: build install
qemu:
	bash "$(ROOT)/scripts/build-install-k3.sh" --only qemu $(K3_ARGS)
sm:
	KEYSTONE_CRYPTO_PROVIDER=unavailable KEYSTONE_RNG_BACKEND=auto bash "$(ROOT)/scripts/build_keystone_sm.sh" "$(ROOT)/keystone" "$(ROOT)/opensbi" "$(K3_BUILD_DIR)/firmware"
opensbi: sm
	KEYSTONE_CRYPTO_PROVIDER=unavailable bash "$(ROOT)/scripts/build_opensbi_link.sh" "$(ROOT)/opensbi" "$(K3_BUILD_DIR)/firmware"
	mkdir -p "$(STAGE)/firmware/k3"
	cp "$(K3_BUILD_DIR)/firmware/build-opensbi-k3-keystone/platform/generic/firmware/"fw_dynamic.* "$(STAGE)/firmware/k3/"
	cp "$(K3_BUILD_DIR)/firmware/sm-combined.o" "$(STAGE)/firmware/k3/"
	cp "$(K3_BUILD_DIR)/firmware/sm-build-options.json" "$(STAGE)/firmware/k3/"
firmware: opensbi
openSBI: opensbi
install-openSBI: install-opensbi
install-erie: install-eyrie
linux:
	bash "$(ROOT)/scripts/build-install-k3.sh" --only linux $(K3_ARGS)
sdk:
	bash "$(ROOT)/scripts/build-install-keystone.sh" --only sdk $(SDK_ARGS)
# Eyrie and examples are built together by the existing SDK workflow.
eyrie: sdk
erie: eyrie
keystone: sm linux eyrie
	bash "$(ROOT)/scripts/build-install-keystone.sh" --only overlay $(SDK_ARGS) --prefix "$(STAGE)" --k3-build-dir "$(K3_BUILD_DIR)"
guest: keystone
rng: eyrie
	KEYSTONE_CRYPTO_PROVIDER=unavailable bash "$(ROOT)/scripts/build-verification-rng.sh" --skip-qemu --skip-sdk --prefix "$(STAGE)" --build-dir "$(KEYSTONE_BUILD_DIR)/rng" --sdk-build-dir "$(KEYSTONE_BUILD_DIR)" --qemu-build-dir "$(K3_BUILD_DIR)" --jobs "$(JOBS)"
crypto: eyrie
	bash "$(ROOT)/scripts/build-keystone-crypto.sh" "$(KEYSTONE_BUILD_DIR)" "$(STAGE)"
verifications: linux eyrie
	$(MAKE) -C "$(ROOT)/verifications" guest $(VERIFY_ARGS)
	$(MAKE) -C "$(ROOT)/verifications" kernel-modules $(VERIFY_ARGS)
samples: eyrie
	$(MAKE) -C "$(ROOT)/samples" all KEYSTONE_BUILD_DIR="$(KEYSTONE_BUILD_DIR)"
install: $(addprefix install-,$(COMPONENTS))
$(addprefix install-,$(COMPONENTS)):
	bash "$(ROOT)/scripts/install-built-keystone.sh" "$(@:install-%=%)" "$(STAGE)" "$(PREFIX)" "$(KEYSTONE_BUILD_DIR)" "$(ROOTFS_ARCHIVE)" "$(ROOTFS_SHA256)"
optee-coexist:
	OPTEE_CLIENT_OUT="$(OPTEE_CLIENT_OUT)" bash "$(ROOT)/scripts/build-k3-optee-coexist.sh"
optee-coexist-test:
	PREFIX="$(abspath $(PREFIX))" KEYSTONE_BUILD_DIR="$(abspath $(KEYSTONE_BUILD_DIR))" \
		KERNEL_OUT="$(abspath $(K3_BUILD_DIR))/linux" OPTEE_CLIENT_OUT="$(OPTEE_CLIENT_OUT)" \
		bash "$(ROOT)/scripts/prepare-k3-optee-coexist-test.sh"
ftpm-ima: optee-coexist
	bash "$(ROOT)/scripts/tests/build-jupiter2-ftpm-ima.sh"
run:
	bash "$(ROOT)/scripts/run-k3.sh" --prefix "$(PREFIX)"
help:
	@echo 'make / make build           Build only (no install/ or rootfs updates)'
	@echo 'make install                Install already-built outputs; no compilation'
	@echo 'make build-install JOBS=4    Build then install in one command'
	@echo 'make qemu|opensbi|sm|eyrie|keystone|crypto|verifications|linux|rng|samples'
	@echo 'make install-qemu|install-opensbi|install-eyrie|install-keystone|install-crypto|install-verifications'
	@echo 'make optee-coexist JOBS=20   Build the OP-TEE Core, coexistence TA and RV64 libteec'
	@echo 'make optee-coexist-test     Generate boot.dtb, boot-pmp16*.dtb and coexist.cpio (OPTEE_CLIENT_OUT overrides client path)'
	@echo 'make ftpm-ima JOBS=20      Build the fTPM TA, supplicant and IMA test kernel/guest program'
	@echo 'Stop QEMU/unmount rootfs before install-keystone. See doc/make-build-install.md.'
