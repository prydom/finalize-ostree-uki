#!/bin/bash
LUKS_BLK_DEVICE=/dev/disk/by-uuid/UUID
systemd-cryptenroll --wipe-slot=tpm2 $LUKS_BLK_DEVICE
systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 --tpm2-public-key-pcrs=11 \
    --tpm2-public-key=/etc/kernel/tpm2-pcr-initrd-rsa2048-public.pem --tpm2-with-pin=yes $LUKS_BLK_DEVICE
