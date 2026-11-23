#!/usr/bin/env python3
import os
import sys

def patch():
    kernel_dir = os.getcwd()
    print(f"[+] Running patch_sukisu.py in {kernel_dir}")

    # 1. Create include/linux/pgtable.h shim
    shim_path = os.path.join(kernel_dir, 'include', 'linux', 'pgtable.h')
    os.makedirs(os.path.dirname(shim_path), exist_ok=True)
    with open(shim_path, 'w', encoding='utf-8') as f:
        f.write('#ifndef _LINUX_PGTABLE_H\n#define _LINUX_PGTABLE_H\n#include <asm/pgtable.h>\n#endif\n')
    print("[+] Created include/linux/pgtable.h shim")

    ksu_dir = os.path.join(kernel_dir, 'KernelSU')
    if not os.path.exists(ksu_dir):
        print(f"[-] KernelSU directory not found at {ksu_dir}")
        return

    # 2. Patch Kconfig: remove mandatory KPROBES dependency if needed
    kconfig_path = os.path.join(ksu_dir, 'kernel', 'Kconfig')
    if os.path.exists(kconfig_path):
        with open(kconfig_path, 'r', encoding='utf-8') as f:
            kc = f.read()
        kc = kc.replace('depends on KPROBES && EXT4_FS', 'depends on EXT4_FS')
        with open(kconfig_path, 'w', encoding='utf-8') as f:
            f.write(kc)
        print("[+] Patched Kconfig")

    # 3. Patch syscall_hook.h for syscall_fn_t
    hook_h = os.path.join(ksu_dir, 'kernel', 'hook', 'syscall_hook.h')
    if os.path.exists(hook_h):
        with open(hook_h, 'r', encoding='utf-8') as f:
            hcontent = f.read()
        if 'typedef void *syscall_fn_t;' not in hcontent:
            target = '#elif defined(__riscv)\ntypedef long (*syscall_fn_t)(const struct pt_regs *);\n#endif'
            repl = '#elif defined(__riscv)\ntypedef long (*syscall_fn_t)(const struct pt_regs *);\n#else\ntypedef void *syscall_fn_t;\n#endif'
            if target in hcontent:
                hcontent = hcontent.replace(target, repl)
            else:
                # Add fallback before #endif
                hcontent = hcontent.replace('#endif', '#ifndef syscall_fn_t\ntypedef void *syscall_fn_t;\n#endif\n#endif', 1)
            with open(hook_h, 'w', encoding='utf-8') as f:
                f.write(hcontent)
            print("[+] Patched syscall_hook.h")

    # 4. Strip MODULE_IMPORT_NS from init.c
    init_c = os.path.join(ksu_dir, 'kernel', 'core', 'init.c')
    if os.path.exists(init_c):
        with open(init_c, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        clean_lines = [l for l in lines if 'MODULE_IMPORT_NS' not in l]
        with open(init_c, 'w', encoding='utf-8') as f:
            f.writelines(clean_lines)
        print("[+] Stripped MODULE_IMPORT_NS from init.c")

    # 5. Add compat code to ksu.h and kernel_compat.h
    compat_code = """
#include <linux/version.h>
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 8, 0)
#include <asm/pgtable.h>
#ifndef strncpy_from_user_nofault
#define strncpy_from_user_nofault(dst, src, count) strncpy_from_user(dst, src, count)
#endif
#ifndef copy_from_user_nofault
#define copy_from_user_nofault(dst, src, count) copy_from_user(dst, src, count)
#endif
#endif
"""
    ksu_h = os.path.join(ksu_dir, 'kernel', 'include', 'ksu.h')
    if os.path.exists(ksu_h):
        with open(ksu_h, 'r', encoding='utf-8') as f:
            kh = f.read()
        if 'strncpy_from_user_nofault' not in kh:
            kh = kh.replace('#define __KSU_H_KSU', '#define __KSU_H_KSU\n' + compat_code)
            with open(ksu_h, 'w', encoding='utf-8') as f:
                f.write(kh)
            print("[+] Added compat defines to ksu.h")

    kc_h = os.path.join(ksu_dir, 'kernel', 'kernel_compat.h')
    if os.path.exists(kc_h):
        with open(kc_h, 'r', encoding='utf-8') as f:
            kch = f.read()
        if 'copy_from_user_nofault' not in kch:
            kch = kch.replace('#define __KSU_H_KERNEL_COMPAT', '#define __KSU_H_KERNEL_COMPAT\n' + compat_code)
            with open(kc_h, 'w', encoding='utf-8') as f:
                f.write(kch)
            print("[+] Added compat defines to kernel_compat.h")

    # 6. Replace any remaining <linux/pgtable.h> with <asm/pgtable.h>
    for root, dirs, files in os.walk(ksu_dir):
        for file in files:
            if file.endswith(('.c', '.h')):
                fp = os.path.join(root, file)
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if '<linux/pgtable.h>' in content:
                    content = content.replace('<linux/pgtable.h>', '<asm/pgtable.h>')
                    with open(fp, 'w', encoding='utf-8') as f:
                        f.write(content)

    print("[+] All SukiSU 4.14 patches applied successfully!")

if __name__ == '__main__':
    patch()
