"""Verify pushed GitHub bytes against Git blobs and create the local review package."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

WORK = Path(__file__).resolve().parent
REPO = WORK / 'supercap-ups-repo'
EVIDENCE = 'sim/tps61088_v1_4/results/'
FOLDERS = ['fsw_internal_probe_50ns', 'fsw_internal_probe_25ns', 'fsw_internal_probe_session']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO)


def gh(*args):
    return subprocess.check_output(['gh', *args], cwd=REPO)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    commit = git('rev-parse', 'HEAD').decode().strip()
    branch = json.loads(gh('api', 'repos/tortletortle/supercap-ups/branches/v1.4-audit-frequency-ilim'))
    assert branch['commit']['sha'] == commit
    pr = json.loads(gh('pr', 'view', '1', '--repo', 'tortletortle/supercap-ups',
                       '--json', 'state,isDraft,headRefName,baseRefName,url'))
    assert pr['state'] == 'OPEN' and pr['isDraft'] and pr['headRefName'] == 'v1.4-audit-frequency-ilim'
    main_sha = json.loads(gh('api', 'repos/tortletortle/supercap-ups/branches/main'))['commit']['sha']
    assert main_sha == '68175218613c45b566fae1db109c13d58f2d5e30'
    archive = WORK / f'github-v14-internal-{commit[:7]}.zip'
    assert not archive.exists()
    with archive.open('wb') as f:
        subprocess.run(['gh', 'api', f'repos/tortletortle/supercap-ups/zipball/{commit}'],
                       cwd=REPO, stdout=f, check=True)
    expected = git('ls-tree', '-r', '--name-only', '-z', commit).decode('utf-8').strip('\0').split('\0')
    request = ''.join(commit + ':' + name + '\n' for name in expected).encode('utf-8')
    batch = subprocess.run(['git', 'cat-file', '--batch'], cwd=REPO, input=request,
                           stdout=subprocess.PIPE, check=True).stdout
    cursor, blobs, records = 0, {}, []
    for name in expected:
        end = batch.index(b'\n', cursor)
        oid, kind, size = batch[cursor:end].split()
        assert kind == b'blob'
        cursor = end + 1
        size = int(size)
        blobs[name] = batch[cursor:cursor + size]
        cursor += size
        assert batch[cursor:cursor + 1] == b'\n'
        cursor += 1
    assert cursor == len(batch)
    output = WORK.parent / 'outputs' / f'supercap-ups-v1.4-internal-{commit[:7]}'
    output.mkdir(exist_ok=False)
    checkout = output / 'repository'
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        prefix = z.namelist()[0].split('/')[0] + '/'
        actual = {n[len(prefix):] for n in z.namelist() if not n.endswith('/')}
        assert actual == set(expected)
        for name in expected:
            data = z.read(prefix + name)
            assert data == blobs[name], name
            records.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
            dest = (checkout / name).resolve()
            assert dest.is_relative_to(checkout.resolve())
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        manifest = json.loads(z.read(prefix + EVIDENCE + 'fsw_internal_probe_session/manifest_sha256.json'))
        for row in manifest['files']:
            data = z.read(prefix + EVIDENCE + row['path'])
            assert len(data) == row['bytes'] and sha(data) == row['sha256'], row['path']
    changed = git('diff-tree', '--no-commit-id', '--name-only', '-r', '-z', commit).decode().strip('\0').split('\0')
    assert not any(Path(p).suffix.lower() in ('.raw', '.db', '.pyc', '.zip') for p in changed)
    report = {'verified_utc': datetime.now(timezone.utc).isoformat(), 'commit': commit,
              'branch': 'v1.4-audit-frequency-ilim', 'remote_branch_matches': True,
              'checked_tracked_files': len(records), 'checked_changed_files': len(changed),
              'checked_evidence_manifest_files': len(manifest['files']),
              'all_remote_bytes_equal_git_blobs': True, 'all_evidence_hashes_match': True,
              'no_RAW_DB_PYC_ZIP_in_new_commit': True, 'main_sha': main_sha,
              'main_unchanged': True, 'pull_request': pr, 'archive_sha256': sha(archive.read_bytes()),
              'files': records}
    (output / 'GitHub文件完整性核验.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    with zipfile.ZipFile(output / '内部探针审查包.zip', 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for folder in FOLDERS:
            for path in sorted((checkout / EVIDENCE / folder).rglob('*')):
                if path.is_file():
                    z.write(path, path.relative_to(checkout / EVIDENCE).as_posix())
        z.write(output / 'GitHub文件完整性核验.json', 'GitHub文件完整性核验.json')
    (output / '交付说明.md').write_text(
        '# TPS61088 V1.4 内部探针审查材料\n\n'
        f'提交：{commit}\n\nGitHub：https://github.com/tortletortle/supercap-ups/commit/{commit}\n\n'
        '两次本机 LTspice 仿真与指定 Python 分析已完成。审查包包含两份原始日志、两份 summary、两份 cycles CSV、comparison，以及实验报告、环境、RAW清单、失败记录和独立核验。完整 RAW 保留本机，未上传。\n\n'
        '[实验报告](repository/sim/tps61088_v1_4/results/fsw_internal_probe_session/实验报告.md)\n\n'
        'GitHub 归档全部文件已与实际 Git blob 逐字节比较；证据文件 SHA-256 也已通过。至此暂停等待审查。\n', encoding='utf-8')
    print(json.dumps({'commit': commit, 'verified_files': len(records),
                      'evidence_files': len(manifest['files']), 'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
