# Boot OSTree Deployments with UEFI Secure Boot and TPM secrets

## finalize-ostree-uki.py

This script parses the Linux Boot Loader Specification (https://uapi-group.org/specifications/specs/boot_loader_specification/) files that OSTree generates and places in /boot/loader/entries. The script generates ephemeral systemd-ukify configurations and executes that tool.

Ukify is used to create a signed Unified Kernel Image (UKI) which when booted can unseal secret bound to a PCR value or policy. UKI images are saved to `$ESP/EFI/Linux` and are intended to be booted with the systemd-boot bootloader.

The entire OSTree repo, deployments, and boot files remain encrypted by LUKS & dm-crypt. Btrfs, ZFS, and/or dm-integrity can be used to ensure integrity at rest.

## Summary

Until I write this process up more completely, here's the cliff notes:

1. Set up LUKS backed block storage for OS and data. Use your distro's documentation for this. I encrypt Btrfs under the LUKS volume.
2. Set up your owner PK with sbctl (https://github.com/Foxboron/sbctl) and sign your existing uefi bootloader. You should also switch from GRUB to systemd-boot at this time. I had this completed from my earlier Fedora Workstation install.
3. Use `create-pcr-keys-rsa2048.sh` and `enroll-pcr-wrapped-key-rsa2048.sh` from this repo to enroll a TPM2 PCR 11 policy and PIN which together seals a LUKS slot secret. Systemd's initrd measures the "ELF kernel image, embedded initrd and other payload of the PE image" into this PCR. This includes the kernel command line options. I additionally include the measured value of TPM 7, which includes the UEFI Secure Boot state. (https://www.freedesktop.org/software/systemd/man/latest/systemd-cryptenroll.html).
4. Use OSTree (https://github.com/ostreedev/ostree) to deploy a stateroot in a new btrfs subvol. This allows you to create a side-by-side installation with an existing traditional Linux install (e.g. Fedora, Arch, Ubuntu).
5. Mount your EFI system partition to /boot/efi.
6. If using upstream Fedora, do the following.
    - Merge the `etc/dracut.conf.d/90-local.conf` from this repo into your OSTree deployment /etc to enable the `systemd-pcrphase` module - to enable measurement into PCR 11.
    - Use `rpm-ostree` to enable initramfs generation during deployment staging.
    - Add package overlays for `sbsigntools`, `systemd-boot-unsigned`, `systemd-ukify`.
7. Use `ostree` or `rpm-ostree` to add `rd.luks.options=tpm2-device=auto` to your kernel boot options.
8. Copy `finalize-ostree-uki.py` to /usr/local/sbin
9. Merge the `etc/systemd/system/ostree-finalize-staged.service.d/override.conf` from this repo into your OSTree deployment /etc. This will run `finalize-ostree-uki.py` when a staged OSTree deployment is finalized.
10. For the first reboot you can use `systemctl daemon-reload && touch /run/ostree/staged-deployment && systemctl stop ostree-finalize-staged.service` to manually trigger an OSTree deployment finalization.
11. Use `sbctl verify` to verify all required EFI binaries are correctly signed. Use `bootctl` to set the deployment for the next boot.
12. Reboot and enter your PIN you enrolled earlier. If done correctly, you should have a trustworthy UEFI Secure Boot & TPM2 setup.

## Resources

### Secure Boot

- https://wiki.archlinux.org/title/Unified_Extensible_Firmware_Interface/Secure_Boot
- https://github.com/Foxboron/sbctl


### UKI

- https://0pointer.net/blog/brave-new-trusted-boot-world.html
- https://wiki.archlinux.org/title/Unified_kernel_image
- https://www.freedesktop.org/software/systemd/man/latest/systemd-cryptenroll.html
- https://www.freedesktop.org/software/systemd/man/latest/ukify.html


### OSTree

- https://ostreedev.github.io/ostree/introduction/
- https://www.aleskandro.com/posts/rpm-ostree-container-native-fedora-silverblue-kinoite-dual-boot/
- https://asamalik.fedorapeople.org/fedora-docs-translations/en-US/fedora-silverblue/installation-dual-boot/
- https://github.com/rhinstaller/anaconda/blob/fedora-39/pyanaconda/modules/payloads/payload/rpm_ostree/installation.py
