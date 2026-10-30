from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath


ARCHIVE_SUFFIXES = {".zip", ".rar"}
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024


class ArchiveError(ValueError):
    """An archive cannot be safely or correctly extracted."""


def safe_extract_archive(
    archive_path: Path,
    target_dir: Path,
    password: str = "",
) -> list[Path]:
    suffix = archive_path.suffix.lower()
    archive_type = _detect_archive_type(archive_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    if archive_type == ".zip":
        return _extract_zip(archive_path, target_dir, password)
    if archive_type == ".rar":
        return _extract_rar(archive_path, target_dir, password)
    if suffix in ARCHIVE_SUFFIXES:
        raise ArchiveError(f"{suffix.upper()[1:]} 文件已损坏，或文件扩展名与实际压缩格式不一致。")
    raise ArchiveError(f"不支持的压缩文件格式：{suffix or '无扩展名'}。")


def _detect_archive_type(archive_path: Path) -> str:
    try:
        with archive_path.open("rb") as source:
            signature = source.read(8)
    except OSError as exc:
        raise ArchiveError(f"无法读取压缩包：{exc}") from exc
    if signature.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return ".zip"
    if signature.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")):
        return ".rar"
    return ""


def _extract_zip(archive_path: Path, target_dir: Path, password: str) -> list[Path]:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            _validate_member_count_and_size(members)
            encrypted = any(member.flag_bits & 0x1 for member in members)
            if encrypted and not password:
                raise ArchiveError("该 ZIP 压缩包已加密，请输入压缩包密码后重新上传。")

            pwd = password.encode("utf-8") if password else None
            extracted: list[Path] = []
            for member in members:
                target = _safe_member_target(target_dir, member.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with archive.open(member, pwd=pwd) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                except RuntimeError as exc:
                    message = str(exc).lower()
                    if "password" in message or "encrypted" in message:
                        raise ArchiveError("ZIP 压缩包密码错误，请检查后重新上传。") from exc
                    raise ArchiveError(f"ZIP 解压失败：{exc}") from exc
                extracted.append(target)
            return extracted
    except zipfile.BadZipFile as exc:
        raise ArchiveError("ZIP 文件已损坏或不是有效的 ZIP 压缩包。") from exc
    except OSError as exc:
        raise ArchiveError(f"无法读取 ZIP 压缩包：{exc}") from exc


def _extract_rar(archive_path: Path, target_dir: Path, password: str) -> list[Path]:
    unrar = _find_unrar()
    if not unrar:
        raise ArchiveError("RAR 解压需要安装 WinRAR/UnRAR，并确保 UnRAR 可执行文件可用。")

    password_option = f"-p{password}" if password else "-p-"
    list_result = _run_unrar([unrar, "lb", password_option, str(archive_path)])
    if list_result.returncode != 0:
        raise _rar_command_error(list_result.returncode, list_result.stderr, password)

    member_names = [line.strip() for line in _decode_output(list_result.stdout).splitlines() if line.strip()]
    if len(member_names) > MAX_ARCHIVE_MEMBERS:
        raise ArchiveError(f"压缩包文件数超过安全上限 {MAX_ARCHIVE_MEMBERS}。")
    for name in member_names:
        _safe_member_target(target_dir, name)

    result = _run_unrar(
        [unrar, "x", "-o+", "-idq", password_option, str(archive_path), f"{target_dir}{os.sep}"],
        timeout=900,
    )
    if result.returncode != 0:
        raise _rar_command_error(result.returncode, result.stderr, password)

    extracted = [path for path in target_dir.rglob("*") if path.is_file()]
    total_size = sum(path.stat().st_size for path in extracted)
    if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
        raise ArchiveError("RAR 解压后总大小超过 4 GB 安全上限。")
    return extracted


def _validate_member_count_and_size(members: list[zipfile.ZipInfo]) -> None:
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise ArchiveError(f"压缩包文件数超过安全上限 {MAX_ARCHIVE_MEMBERS}。")
    if sum(member.file_size for member in members) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
        raise ArchiveError("压缩包解压后总大小超过 4 GB 安全上限。")
    for member in members:
        _safe_member_target(Path.cwd(), member.filename, resolve_root=False)


def _safe_member_target(root: Path, member_name: str, *, resolve_root: bool = True) -> Path:
    normalized = member_name.replace("\\", "/")
    member = PurePosixPath(normalized)
    if member.is_absolute() or ".." in member.parts or (member.parts and ":" in member.parts[0]):
        raise ArchiveError("压缩包包含不安全路径，已拒绝解压。")
    target = root.joinpath(*member.parts)
    if resolve_root and not target.resolve().is_relative_to(root.resolve()):
        raise ArchiveError("压缩包包含不安全路径，已拒绝解压。")
    return target


def _find_unrar() -> str | None:
    configured = os.getenv("UNRAR_TOOL", "").strip()
    candidates = [
        configured,
        shutil.which("unrar") or "",
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
    ]
    return next((item for item in candidates if item and Path(item).is_file()), None)


def _run_unrar(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ArchiveError("RAR 解压超时，请检查压缩包大小或完整性。") from exc
    except OSError as exc:
        raise ArchiveError(f"无法启动 RAR 解压工具：{exc}") from exc


def _rar_command_error(returncode: int, stderr: bytes, password: str) -> ArchiveError:
    detail = _decode_output(stderr).strip()
    if returncode in {3, 10}:
        return ArchiveError("RAR 文件已损坏或不是有效的 RAR 压缩包。")
    if returncode == 11 or "password" in detail.lower():
        return ArchiveError("RAR 压缩包密码错误，请检查后重新上传。" if password else "该 RAR 压缩包已加密，请输入压缩包密码后重新上传。")
    return ArchiveError(f"RAR 解压失败（错误码 {returncode}）{f'：{detail}' if detail else ''}")


def _decode_output(value: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "cp437"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")
