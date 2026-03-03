tpm2_startup -c
tpm2_createprimary -c primary.ctx
dd if=/dev/urandom bs=1 count=128 of=sym.key
tpm2_create -C primary.ctx -i sym.key -u key.pub -r key.priv
tpm2_load -C primary.ctx -u key.pub -r key.priv -c key.ctx
tpm2 unseal -c key.ctx > sym.key1
