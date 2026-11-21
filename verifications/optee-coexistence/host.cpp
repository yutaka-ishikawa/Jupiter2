// SPDX-License-Identifier: BSD-2-Clause
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <tee_client_api.h>
#include "host/Enclave.hpp"
#include "edge/edge_call.h"
#include "protocol.h"

static TEEC_Session session;
static uint32_t sequence;
static unsigned int ocall_count;
static bool ocall_ok;

static bool check_ta(void)
{
    TEEC_Operation operation = {};
    uint32_t origin = 0;
    TEEC_Result status;

    operation.paramTypes = TEEC_PARAM_TYPES(TEEC_VALUE_INOUT, TEEC_NONE,
					    TEEC_NONE, TEEC_NONE);
    operation.params[0].value.a = sequence;
    status = TEEC_InvokeCommand(&session, COEXISTENCE_CMD_INCREMENT,
				&operation, &origin);
    if (status != TEEC_SUCCESS ||
	operation.params[0].value.a != sequence + 1 ||
	operation.params[0].value.b != COEXISTENCE_TA_MARKER) {
	std::fprintf(stderr, "TA check %u failed: result=%#x origin=%u\n",
		     sequence, status, origin);
	return false;
    }
    sequence++;
    return true;
}

static void dispatch(void *buffer)
{
    auto *call = static_cast<struct edge_call *>(buffer);
    const char expected[] = "Hello World";
    uintptr_t args;
    uintptr_t reply;
    uintptr_t result = sizeof(expected) - 1;
    size_t size;

    call->return_data.call_status = CALL_STATUS_BAD_OFFSET;
    ocall_count++;
    if (call->call_id != 1 || edge_call_args_ptr(call, &args, &size) ||
	size != sizeof(expected) ||
	std::memcmp(reinterpret_cast<const void *>(args), expected, size)) {
	return;
    }
    reply = edge_call_data_ptr();
    if (edge_call_check_ptr_valid(reply, sizeof(result)) || !check_ta()) {
	return;
    }
    std::memcpy(reinterpret_cast<void *>(reply), &result, sizeof(result));
    if (edge_call_setup_ret(call, reinterpret_cast<void *>(reply),
			    sizeof(result))) {
	return;
    }
    ocall_ok = true;
    call->return_data.call_status = CALL_STATUS_OK;
}

static bool check_enclave(char **images)
{
    Keystone::Enclave enclave;
    Keystone::Params params;
    uintptr_t result = UINTPTR_MAX;
    Keystone::Error status;
    bool destroyed;

    params.setFreeMemSize(2 * 1024 * 1024);
    params.setUntrustedSize(256 * 1024);
    status = enclave.init(images[0], images[1], images[2], params);
    if (status != Keystone::Error::Success) {
	std::fprintf(stderr, "Enclave initialization failed: %d\n",
		     static_cast<int>(status));
	return false;
    }
    edge_call_init_internals(
	reinterpret_cast<uintptr_t>(enclave.getSharedBuffer()),
	enclave.getSharedBufferSize());
    enclave.registerOcallDispatch(dispatch);
    ocall_ok = false;
    ocall_count = 0;
    status = enclave.run(&result);
    if (status != Keystone::Error::Success) {
	std::fprintf(stderr, "Enclave execution failed: %d\n",
		     static_cast<int>(status));
	return false;
    }
    destroyed = enclave.destroy() == Keystone::Error::Success;
    if (!destroyed || result || !ocall_ok || ocall_count != 1) {
	std::fprintf(stderr, "Enclave check failed: exit=%lu ocalls=%u\n",
		     static_cast<unsigned long>(result), ocall_count);
	return false;
    }
    return true;
}

int main(int argc, char **argv)
{
    TEEC_Context context;
    const TEEC_UUID uuid = COEXISTENCE_TA_UUID;
    uint32_t origin = 0;
    TEEC_Result status;
    bool ok;
    unsigned int iteration;

    if (argc != 4) {
	std::fprintf(stderr, "Usage: %s HELLO_NATIVE EYRIE LOADER\n", argv[0]);
	return 2;
    }
    status = TEEC_InitializeContext(nullptr, &context);
    if (status != TEEC_SUCCESS) {
	std::fprintf(stderr, "TEEC_InitializeContext: %#x\n", status);
	return 1;
    }
    status = TEEC_OpenSession(&context, &session, &uuid, TEEC_LOGIN_PUBLIC,
			      nullptr, nullptr, &origin);
    if (status != TEEC_SUCCESS) {
	std::fprintf(stderr, "TEEC_OpenSession: %#x origin=%u\n", status,
		     origin);
	TEEC_FinalizeContext(&context);
	return 1;
    }
    ok = check_ta();
    for (iteration = 0; ok && iteration < 16; iteration++) {
	ok = check_enclave(argv + 1) && check_ta();
    }
    TEEC_CloseSession(&session);
    TEEC_FinalizeContext(&context);
    if (!ok) {
	return 1;
    }
    std::printf("PASS: %u enclave runs, %u TA calls including OCALL\n",
		iteration, sequence);
    return 0;
}
