tpm2_startup -c
tpm2_nvdefine -C o -s 45 -a "ownerread|policywrite|ownerwrite" 1
tpm2_nvwrite -C o -i /etc/wireguard/privatekey 1
