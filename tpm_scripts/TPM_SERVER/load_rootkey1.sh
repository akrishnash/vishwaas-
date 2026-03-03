tpm2_nvdefine -C o -s 128 -a "ownerread|policywrite|ownerwrite" 2
tpm2_nvwrite -C o -i sym.key 2
