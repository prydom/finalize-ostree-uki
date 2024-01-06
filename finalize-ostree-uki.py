#!/usr/bin/env python3

from pathlib import Path
from typing import *
import shlex
import os
import tempfile
import argparse
import subprocess

# ---- CONFIGURE ME ----
SECUREBOOT_PRIVATE_KEY_PATH = '/var/lib/sbctl/keys/db/db.key'
SECUREBOOT_PUBLIC_KEY_PATH = '/var/lib/sbctl/keys/db/db.pem'
PCR_PRIVATE_KEY_PATH = '/etc/kernel/tpm2-pcr-initrd-rsa2048-private.pem'
PCR_PUBLIC_KEY_PATH = '/etc/kernel/tpm2-pcr-initrd-rsa2048-public.pem'
# ---- END CONFIGURE ME ----

REQUIRED_BOOT_ENTRY_OPTIONS = ["title", "options", "linux", "initrd"]

def generateUkifyOptions(linuxKernelPath: str, initrdPaths: list[Path],
                         kernelOptions: str, uname:str, osReleasePath: str) -> str:
    return f'''[UKI]
Linux={linuxKernelPath}
Initrd={' '.join(map(shlex.quote, initrdPaths))}
Uname={uname}
Cmdline={kernelOptions}
OSRelease=@{osReleasePath}
SecureBootPrivateKey={SECUREBOOT_PRIVATE_KEY_PATH}
SecureBootCertificate={SECUREBOOT_PUBLIC_KEY_PATH}
PCRPKey={PCR_PUBLIC_KEY_PATH}
PCRBanks=sha256

[PCRSignature:initrd]
PCRPrivateKey={PCR_PRIVATE_KEY_PATH}
PCRPublicKey={PCR_PUBLIC_KEY_PATH}
Phases=enter-initrd'''

def fsyncPath(path: Union[str, Path]) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    os.fsync(fd)
    os.close(fd)

def getOSTreeDeployment(kernelOptions: str) -> Optional[str]:
    for option in kernelOptions.split():
        if option.startswith('ostree='):
            return option.partition('ostree=')[2]

def buildUkiFileName(entryPath: Path) -> str:
    entryName = entryPath.name
    entryName = entryName.rpartition('.')[0]+'.efi'
    return entryName

def runUkify(ukifyOptions: str, output: Path, verbose: bool) -> None:
    with tempfile.NamedTemporaryFile(delete_on_close=False) as ukifyOptionsFile:
        ukifyOptionsFile.write(ukifyOptions.encode('utf-8'))
        ukifyOptionsFile.close()

        swapUkiFilename = str(output)+'_swap'
        process = subprocess.run(['/usr/lib/systemd/ukify', 'build',
                                  '--config', ukifyOptionsFile.name,
                                  '--output', swapUkiFilename], capture_output=True)

        if process.returncode != 0:
            print(f"ERROR: ukify returned a non-zero return code: {process.returncode}")
            print(f'failed processing {output}')
            print(f'options:\n{ukifyOptions}')
            print(process.stdout.decode('utf-8'))
            try:
                os.remove(swapUkiFilename)
            except:
                print(f'WARNING: failed to cleanup {swapUkiFilename}')
            return
        elif verbose:
            print(f'--- processing {output}')
            print(f'options:\n{ukifyOptions}')
            print(process.stdout.decode('utf-8'))

    try:
        fsyncPath(swapUkiFilename)
        os.rename(swapUkiFilename, output)
        fsyncPath(output)
    except Exception as e:
        print(f"ERROR: Failed to rename {swapUkiFilename} to {output}, {e}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--outputDir', help='Where to save the UKI binaries, defaults to /boot/efi/EFI/Linux',
                        default=Path('/boot/efi/EFI/Linux'), type=Path)
    parser.add_argument('--ukify', help='Where the ukify binary is found, defaults to /usr/lib/systemd/ukify',
                        default='/usr/lib/systemd/ukify')
    parser.add_argument('--verbose', help='Print output from ukify', action='store_true')
    args = parser.parse_args()

    if not args.outputDir.is_dir():
        print(f'ERROR: {args.outputDir} is not a directory')

    for entryPath in Path('/boot/loader/entries').glob('*.conf'):
        if not entryPath.is_file():
            continue
        with entryPath.open() as entryFile:
            entry = entryFile.read().splitlines()
            parsedEntry: dict[str, Union[str, list[str]]] = {}
            for line in entry:
                split = line.split(maxsplit=1)
                if len(split) == 0 or split[0].startswith('#'):
                    continue
                elif split[0] in parsedEntry:
                    if split[0] == 'initrd':
                        parsedEntry['initrd'].append('/boot'+split[1])
                    else:
                        print(f'WARNING: Duplicated entry key {split[0]}')
                elif split[0] == 'initrd':
                    parsedEntry['initrd'] = ['/boot'+split[1]]
                else:
                    parsedEntry[split[0]] = split[1]

            missing = False
            for option in REQUIRED_BOOT_ENTRY_OPTIONS:
                if not option in parsedEntry:
                    print(f'ERROR: Missing entry key {option} for {entryPath}')
                    missing = True
            if missing:
                print(f"Skipping {entryPath}")
                continue

            kernelOptions = parsedEntry['options']
            ostreeDeployment = getOSTreeDeployment(kernelOptions)
            if ostreeDeployment is None:
                print(f"ERROR: Boot loader entry {entryPath} is not booting an OSRoot deployment.")
                continue

            ostreeDeploymentPath = Path(ostreeDeployment)
            if ostreeDeploymentPath.exists():
                osReleasePath = ostreeDeploymentPath.joinpath('usr/lib/os-release')
                if not osReleasePath.exists():
                    print(f'ERROR: Missing os-release {osReleasePath} for {entryPath}')
                    continue
                unamePathGlob = list(ostreeDeploymentPath.joinpath('usr/lib/modules').glob('*'))
                if len(unamePathGlob) != 1:
                    print(f'ERROR: multiple kernels in deployment {osReleasePath} for {entryPath}')
                    continue
                kernelUname = unamePathGlob[0].name

                osReleasePartition = [line.partition('=') for line in osReleasePath.read_text().splitlines()]
                osRelease = {key:value for key, _, value in osReleasePartition}
                osRelease['PRETTY_NAME'] = parsedEntry['title']

                with tempfile.NamedTemporaryFile(delete_on_close=False) as osReleaseTmpFile:
                    osReleaseStr = '\n'.join( [f"{key}={value}" for key, value in osRelease.items()] )
                    osReleaseTmpFile.write(osReleaseStr.encode('utf-8'))
                    osReleaseTmpFile.close()

                    ukifyOptions = generateUkifyOptions('/boot'+parsedEntry['linux'], parsedEntry['initrd'],
                                                        kernelOptions, kernelUname, osReleaseTmpFile.name)
                    outputFilePath = args.outputDir.joinpath(buildUkiFileName(entryPath))
                    runUkify(ukifyOptions, outputFilePath, args.verbose)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
