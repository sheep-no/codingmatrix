#!/usr/bin/env python3
"""
日志管理工具

用于手动维护日志文件，支持清理、压缩、查看统计信息等操作。

使用方式:
    python scripts/manage_logs.py clean     # 清理过期日志
    python scripts/manage_logs.py compress  # 压缩旧日志
    python scripts/manage_logs.py stats     # 查看统计信息
    python scripts/manage_logs.py list      # 列出所有日志文件
    python scripts/manage_logs.py clean --days=15  # 清理 15 天前的日志

依赖:
    pip install pyyaml
"""
import argparse
import gzip
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path("logs")


def get_log_files():
    """获取所有日志文件"""
    if not LOG_DIR.exists():
        return []
    
    files = []
    for pattern in ["*.log", "*.log.*", "*.gz"]:
        files.extend(LOG_DIR.glob(pattern))
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def clean_logs(days=30, dry_run=False):
    """
    清理过期日志文件
    
    Args:
        days: 保留最近多少天的日志
        dry_run: 如果为 True，只显示不删除
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted_count = 0
    deleted_size = 0
    
    print(f"扫描日志目录：{LOG_DIR.absolute()}")
    print(f"清理阈值：{days} 天前 ({cutoff.strftime('%Y-%m-%d')})")
    print("-" * 60)
    
    for log_file in get_log_files():
        try:
            file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            
            if file_mtime < cutoff:
                file_size = log_file.stat().st_size
                if not dry_run:
                    log_file.unlink()
                deleted_count += 1
                deleted_size += file_size
                status = "删除" if not dry_run else "待删除"
                print(f"  {status}: {log_file.name} ({format_size(file_size)})")
        
        except Exception as e:
            print(f"  错误：{log_file.name} - {e}")
    
    print("-" * 60)
    action = "将删除" if not dry_run else "拟删除"
    print(f"{action}: {deleted_count} 个文件，释放 {format_size(deleted_size)}")


def compress_logs(days=3, dry_run=False):
    """
    压缩旧日志文件
    
    Args:
        days: 压缩多少天前的日志
        dry_run: 如果为 True，只显示不压缩
    """
    threshold = datetime.utcnow() - timedelta(days=days)
    compressed_count = 0
    saved_size = 0
    
    print(f"扫描日志目录：{LOG_DIR.absolute()}")
    print(f"压缩阈值：{days} 天前 ({threshold.strftime('%Y-%m-%d')})")
    print("-" * 60)
    
    for log_file in get_log_files():
        if log_file.name.endswith('.gz'):
            continue
        
        try:
            file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            
            if file_mtime < threshold:
                original_size = log_file.stat().st_size
                compressed_file = LOG_DIR / f"{log_file.name}.gz"
                
                if not dry_run:
                    with open(log_file, 'rb') as f_in:
                        with gzip.open(compressed_file, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    
                    compressed_size = compressed_file.stat().st_size
                    log_file.unlink()
                    saved_size += original_size - compressed_size
                    compression_rate = (1 - compressed_size / original_size) * 100
                    print(f"  压缩：{log_file.name} -> {compressed_file.name}")
                    print(f"        原始：{format_size(original_size)}, "
                          f"压缩后：{format_size(compressed_size)}, "
                          f"压缩率：{compression_rate:.1f}%")
                else:
                    print(f"  待压缩：{log_file.name} ({format_size(original_size)})")
                
                compressed_count += 1
        
        except Exception as e:
            print(f"  错误：{log_file.name} - {e}")
    
    print("-" * 60)
    print(f"处理完成：{compressed_count} 个文件")
    if not dry_run and saved_size > 0:
        print(f"节省空间：{format_size(saved_size)}")


def show_stats():
    """显示日志统计信息"""
    if not LOG_DIR.exists():
        print("日志目录不存在")
        return
    
    files = get_log_files()
    total_size = sum(f.stat().st_size for f in files)
    
    gz_files = [f for f in files if f.name.endswith('.gz')]
    log_files = [f for f in files if not f.name.endswith('.gz')]
    
    print("=" * 60)
    print("日志统计信息")
    print("=" * 60)
    print(f"日志目录：{LOG_DIR.absolute()}")
    print(f"总文件数：{len(files)}")
    print(f"  - 日志文件：{len(log_files)}")
    print(f"  - 压缩文件：{len(gz_files)}")
    print(f"总大小：{format_size(total_size)}")
    print()
    
    if log_files:
        print("最新日志文件:")
        for f in log_files[:5]:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            size = f.stat().st_size
            print(f"  {f.name:30} {format_size(size):>10}  {mtime.strftime('%Y-%m-%d %H:%M')}")
    
    print()
    if gz_files:
        print("压缩文件:")
        for f in gz_files[:5]:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            size = f.stat().st_size
            print(f"  {f.name:30} {format_size(size):>10}  {mtime.strftime('%Y-%m-%d %H:%M')}")
    
    if len(files) > 10:
        print(f"  ... 还有 {len(files) - 10} 个文件")


def list_logs():
    """列出所有日志文件"""
    if not LOG_DIR.exists():
        print("日志目录不存在")
        return
    
    files = get_log_files()
    
    print("=" * 80)
    print("日志文件列表")
    print("=" * 80)
    print(f"{'文件名':<40} {'大小':>12} {'修改时间':<20}")
    print("-" * 80)
    
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size = f.stat().st_size
        print(f"{f.name:<40} {format_size(size):>12}  {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("-" * 80)
    print(f"总计：{len(files)} 个文件")


def format_size(size_bytes):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def main():
    parser = argparse.ArgumentParser(
        description="日志管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python manage_logs.py clean            # 清理 30 天前的日志
  python manage_logs.py clean --days=15  # 清理 15 天前的日志
  python manage_logs.py clean --dry-run  # 只显示不删除
  python manage_logs.py compress         # 压缩 3 天前的日志
  python manage_logs.py stats            # 查看统计信息
  python manage_logs.py list             # 列出所有日志文件
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    clean_parser = subparsers.add_parser("clean", help="清理过期日志")
    clean_parser.add_argument("--days", type=int, default=30, help="保留天数 (默认：30)")
    clean_parser.add_argument("--dry-run", action="store_true", help="只显示不删除")
    
    compress_parser = subparsers.add_parser("compress", help="压缩旧日志")
    compress_parser.add_argument("--days", type=int, default=3, help="压缩天数 (默认：3)")
    compress_parser.add_argument("--dry-run", action="store_true", help="只显示不压缩")
    
    subparsers.add_parser("stats", help="查看统计信息")
    subparsers.add_parser("list", help="列出所有日志文件")
    
    args = parser.parse_args()
    
    if args.command == "clean":
        clean_logs(days=args.days, dry_run=args.dry_run)
    elif args.command == "compress":
        compress_logs(days=args.days, dry_run=args.dry_run)
    elif args.command == "stats":
        show_stats()
    elif args.command == "list":
        list_logs()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
