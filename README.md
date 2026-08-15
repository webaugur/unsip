# unsip

Throttled unzip. Same flag letters as Info-ZIP `unzip`, plus periodic `fsync`
and a short pause so writeback can drain on spinning disks and ZFS pools.

`unsip` is not an upstream name.

## Install

```bash
pip install git+https://github.com/webaugur/unsip.git
# or
git clone https://github.com/webaugur/unsip.git
cd unsip
ln -sfn "$PWD/bin/unsip" ~/bin/unsip
```

## Usage

```bash
unsip [-nqojltv] file.zip [file(s) ...] [-x xfile(s) ...] [-d exdir]
unsip --sync-every 4194304 --pause 1 -d dest archive.zip
```

| Flag | Meaning |
| --- | --- |
| `-d DIR` | extract into DIR |
| `-n` | never overwrite existing files |
| `-o` | overwrite without prompting |
| `-j` | junk paths |
| `-l` | list |
| `-t` | test CRC |
| `-q` | quiet |
| `-v` | verbose |
| `--sync-every BYTES` | fsync after this many uncompressed bytes (default 8 MiB) |
| `--pause SECONDS` | sleep after each sync (default 0.4) |

Default extract mode skips a file that already exists with the same size
(resume-friendly). Incomplete leftovers ending in `.extract` are replaced.

## License

MIT
