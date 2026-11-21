/* SPDX-License-Identifier: BSD-2-Clause */
#include <tee_internal_api.h>
#include "protocol.h"

TEE_Result TA_CreateEntryPoint(void)
{
    return TEE_SUCCESS;
}

void TA_DestroyEntryPoint(void)
{
}

TEE_Result TA_OpenSessionEntryPoint(uint32_t types, TEE_Param params[4],
				   void **context)
{
    (void)params;
    *context = NULL;
    if (types != TEE_PARAM_TYPES(TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE,
				 TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE)) {
	return TEE_ERROR_BAD_PARAMETERS;
    }
    return TEE_SUCCESS;
}

void TA_CloseSessionEntryPoint(void *context)
{
    (void)context;
}

TEE_Result TA_InvokeCommandEntryPoint(void *context, uint32_t command,
				     uint32_t types, TEE_Param params[4])
{
    (void)context;
    if (command != COEXISTENCE_CMD_INCREMENT) {
	return TEE_ERROR_NOT_SUPPORTED;
    }
    if (types != TEE_PARAM_TYPES(TEE_PARAM_TYPE_VALUE_INOUT,
				 TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE,
				 TEE_PARAM_TYPE_NONE)) {
	return TEE_ERROR_BAD_PARAMETERS;
    }
    params[0].value.a++;
    params[0].value.b = COEXISTENCE_TA_MARKER;
    return TEE_SUCCESS;
}
