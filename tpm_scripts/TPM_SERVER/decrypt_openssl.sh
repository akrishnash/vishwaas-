#tpm2_startup
#openssl enc -e -aes128 -kfile sym.key2 -in graph.pikle.enc -out graph.pikle.dec
openssl enc -d -aes128 -kfile sym.key2 -in data.enc -out data.out
