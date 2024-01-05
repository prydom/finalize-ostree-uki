#!/bin/bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out /etc/kernel/tpm2-pcr-initrd-private.pem
openssl rsa -pubout -in /etc/kernel/tpm2-pcr-initrd-private.pem -out /etc/kernel/tpm2-pcr-initrd-public.pem
