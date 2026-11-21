.DEFAULT_GOAL := guest
KEYSTONE_BUILD_DIR ?= ../../.build-keystone
SDK_DIR ?= $(KEYSTONE_BUILD_DIR)/sdk-install
CROSS_COMPILE ?= riscv64-linux-gnu-
OPTEE_CLIENT_OUT ?=
TA_DEV_KIT_DIR ?=
OUT := $(CURDIR)/build
SDK_LIBS := $(SDK_DIR)/lib/libkeystone-host.a $(SDK_DIR)/lib/libkeystone-edge.a

ifeq ($(origin CXX),default)
CXX := $(CROSS_COMPILE)g++
endif

.PHONY: guest ta clean
guest: $(OUT)/optee-coexistence ta

$(OUT)/optee-coexistence: host.cpp protocol.h $(SDK_LIBS) Makefile
	test -n "$(OPTEE_CLIENT_OUT)"
	mkdir -p "$(OUT)"
	$(CXX) $(CPPFLAGS) -I"$(SDK_DIR)/include" -I"$(OPTEE_CLIENT_OUT)/include" \
	    $(CXXFLAGS) -std=c++17 -Wall -Wextra $(LDFLAGS) -o "$@" "$<" \
	    $(SDK_LIBS) -L"$(OPTEE_CLIENT_OUT)/lib" -lteec $(LDLIBS)

ta:
	test -n "$(TA_DEV_KIT_DIR)"
	$(MAKE) -C ta O="$(OUT)/ta" TA_DEV_KIT_DIR="$(abspath $(TA_DEV_KIT_DIR))" \
	    CROSS_COMPILE="$(CROSS_COMPILE)"

clean:
	rm -rf "$(OUT)"
