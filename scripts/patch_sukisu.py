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

    # 2. Patch kernel include/linux/poll.h for __poll_t and EPOLL definitions
    poll_h = os.path.join(kernel_dir, 'include', 'linux', 'poll.h')
    if os.path.exists(poll_h):
        with open(poll_h, 'r', encoding='utf-8') as f:
            ph = f.read()
        if '__poll_t' not in ph:
            ph = ph.replace('#include <uapi/linux/poll.h>', '#include <uapi/linux/poll.h>\n#include <uapi/linux/eventpoll.h>\n#ifndef __poll_t\ntypedef unsigned int __poll_t;\n#endif')
            with open(poll_h, 'w', encoding='utf-8') as f:
                f.write(ph)
            print("[+] Added __poll_t and eventpoll.h to include/linux/poll.h")

    ksu_dir = os.path.join(kernel_dir, 'KernelSU')
    if not os.path.exists(ksu_dir):
        print(f"[-] KernelSU directory not found at {ksu_dir}")
        return

    # 3. Patch Kconfig: remove mandatory KPROBES dependency if needed
    kconfig_path = os.path.join(ksu_dir, 'kernel', 'Kconfig')
    if os.path.exists(kconfig_path):
        with open(kconfig_path, 'r', encoding='utf-8') as f:
            kc = f.read()
        kc = kc.replace('depends on KPROBES && EXT4_FS', 'depends on EXT4_FS')
        with open(kconfig_path, 'w', encoding='utf-8') as f:
            f.write(kc)
        print("[+] Patched Kconfig")

    # 4. Patch syscall_hook.h for syscall_fn_t function pointer typedef
    hook_h = os.path.join(ksu_dir, 'kernel', 'hook', 'syscall_hook.h')
    if os.path.exists(hook_h):
        with open(hook_h, 'r', encoding='utf-8') as f:
            hcontent = f.read()
        target = '#elif defined(__riscv)\ntypedef long (*syscall_fn_t)(const struct pt_regs *);\n#endif'
        repl = '#elif defined(__riscv)\ntypedef long (*syscall_fn_t)(const struct pt_regs *);\n#else\ntypedef long (*syscall_fn_t)(const struct pt_regs *);\n#endif'
        if target in hcontent:
            hcontent = hcontent.replace(target, repl)
        elif 'typedef void *syscall_fn_t;' in hcontent:
            hcontent = hcontent.replace('typedef void *syscall_fn_t;', 'typedef long (*syscall_fn_t)(const struct pt_regs *);')
        else:
            hcontent = hcontent.replace('#endif', '#ifndef syscall_fn_t\ntypedef long (*syscall_fn_t)(const struct pt_regs *);\n#endif\n#endif', 1)
        with open(hook_h, 'w', encoding='utf-8') as f:
            f.write(hcontent)
        print("[+] Patched syscall_hook.h with valid function pointer typedef")

    # 5. Strip MODULE_IMPORT_NS from init.c
    init_c = os.path.join(ksu_dir, 'kernel', 'core', 'init.c')
    if os.path.exists(init_c):
        with open(init_c, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        clean_lines = [l for l in lines if 'MODULE_IMPORT_NS' not in l]
        with open(init_c, 'w', encoding='utf-8') as f:
            f.writelines(clean_lines)
        print("[+] Stripped MODULE_IMPORT_NS from init.c")

    # 6. Add compat code to ksu.h and kernel_compat.h
    compat_code = """
#include <linux/version.h>
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 8, 0)
#include <asm/pgtable.h>
#include <uapi/linux/eventpoll.h>
#ifndef __poll_t
typedef unsigned int __poll_t;
#endif
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

    # 7. Replace any remaining <linux/pgtable.h> with <asm/pgtable.h>
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

    # 8. Patch lsm_hook.c for Linux 4.14 list_head compatibility
    lsm_c = os.path.join(ksu_dir, 'kernel', 'hook', 'lsm_hook.c')
    if os.path.exists(lsm_c):
        with open(lsm_c, 'r', encoding='utf-8') as f:
            lc = f.read()
        
        target1 = 'hook->list.head = head;\n                    hook->list.list.next = NULL;\n                    hook->list.list.pprev = &head->first;'
        repl1 = '''hook->list.head = (void *)head;
#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0)
                    hook->list.list.next = (struct list_head *)head;
                    hook->list.list.prev = (struct list_head *)head;
#else
                    hook->list.list.next = NULL;
                    hook->list.list.pprev = &head->first;
#endif'''
        if target1 in lc:
            lc = lc.replace(target1, repl1)

        target2 = 'hook->list.head = head;\n                hook->list.list.next = NULL;\n                hook->list.list.pprev = &head->first;'
        repl2 = '''hook->list.head = (void *)head;
#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0)
                hook->list.list.next = (struct list_head *)head;
                hook->list.list.prev = (struct list_head *)head;
#else
                hook->list.list.next = NULL;
                hook->list.list.pprev = &head->first;
#endif'''
        if target2 in lc:
            lc = lc.replace(target2, repl2)

        target3 = 'list_del_rcu(&pos->list.list);'
        repl3 = '''#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0)
        list_del_rcu((struct list_head *)&pos->list.list);
#else
        list_del_rcu(&pos->list.list);
#endif'''
        if target3 in lc:
            lc = lc.replace(target3, repl3)

        with open(lsm_c, 'w', encoding='utf-8') as f:
            f.write(lc)
        print("[+] Patched lsm_hook.c for Linux 4.14 list_head compatibility")

    # 9. Patch file_wrapper.c for Linux 4.14 fops and types
    fw_c = os.path.join(ksu_dir, 'kernel', 'infra', 'file_wrapper.c')
    if os.path.exists(fw_c):
        with open(fw_c, 'r', encoding='utf-8') as f:
            fc = f.read()
        
        if '__poll_t' not in fc:
            fc = '#include <uapi/linux/eventpoll.h>\n#ifndef __poll_t\ntypedef unsigned int __poll_t;\n#endif\n' + fc

        fc = fc.replace('unsigned int ksu_wrapper_iopoll(struct file *fp, struct io_comp_batch *b, unsigned int flags)',
                        '#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 1, 0)\nunsigned int ksu_wrapper_iopoll(struct file *fp, struct io_comp_batch *b, unsigned int flags)')
        fc = fc.replace('p->ops.iopoll = fp->f_op->iopoll ? ksu_wrapper_iopoll : NULL;',
                        '#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 1, 0)\n    p->ops.iopoll = fp->f_op->iopoll ? ksu_wrapper_iopoll : NULL;\n#endif')

        remap_target = '''static loff_t ksu_wrapper_remap_file_range(struct file *file_in, loff_t pos_in, struct file *file_out, loff_t pos_out,
                                           loff_t len, unsigned int remap_flags)
{
    if (remap_flags & REMAP_FILE_DEDUP) {
        struct ksu_file_wrapper *data = file_out->private_data;
        struct file *orig = data->orig;
        return orig->f_op->remap_file_range(file_in, pos_in, orig, pos_out, len, remap_flags);
    } else {
        struct ksu_file_wrapper *data = file_in->private_data;
        struct file *orig = data->orig;
        return orig->f_op->remap_file_range(orig, pos_in, file_out, pos_out, len, remap_flags);
    }
}'''
        remap_repl = '''#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 20, 0)
static loff_t ksu_wrapper_remap_file_range(struct file *file_in, loff_t pos_in, struct file *file_out, loff_t pos_out,
                                           loff_t len, unsigned int remap_flags)
{
    if (remap_flags & REMAP_FILE_DEDUP) {
        struct ksu_file_wrapper *data = file_out->private_data;
        struct file *orig = data->orig;
        return orig->f_op->remap_file_range(file_in, pos_in, orig, pos_out, len, remap_flags);
    } else {
        struct ksu_file_wrapper *data = file_in->private_data;
        struct file *orig = data->orig;
        return orig->f_op->remap_file_range(orig, pos_in, file_out, pos_out, len, remap_flags);
    }
}
#endif'''
        if remap_target in fc:
            fc = fc.replace(remap_target, remap_repl)

        fc = fc.replace('p->ops.remap_file_range = fp->f_op->remap_file_range ? ksu_wrapper_remap_file_range : NULL;',
                        '#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 20, 0)\n    p->ops.remap_file_range = fp->f_op->remap_file_range ? ksu_wrapper_remap_file_range : NULL;\n#endif')

        fadvise_target = '''static int ksu_wrapper_fadvise(struct file *fp, loff_t off1, loff_t off2, int flags)
{
    struct ksu_file_wrapper *data = fp->private_data;
    struct file *orig = data->orig;
    if (orig->f_op->fadvise) {
        return orig->f_op->fadvise(orig, off1, off2, flags);
    }
    return -EINVAL;
}'''
        fadvise_repl = '''#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 0, 0)
static int ksu_wrapper_fadvise(struct file *fp, loff_t off1, loff_t off2, int flags)
{
    struct ksu_file_wrapper *data = fp->private_data;
    struct file *orig = data->orig;
    if (orig->f_op->fadvise) {
        return orig->f_op->fadvise(orig, off1, off2, flags);
    }
    return -EINVAL;
}
#endif'''
        if fadvise_target in fc:
            fc = fc.replace(fadvise_target, fadvise_repl)

        fc = fc.replace('p->ops.fadvise = fp->f_op->fadvise ? ksu_wrapper_fadvise : NULL;',
                        '#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 0, 0)\n    p->ops.fadvise = fp->f_op->fadvise ? ksu_wrapper_fadvise : NULL;\n#endif')

        with open(fw_c, 'w', encoding='utf-8') as f:
            f.write(fc)
        print("[+] Patched file_wrapper.c for Linux 4.14 fops")

    # 10. Patch event_queue.h for __poll_t and eventpoll.h
    eq_h = os.path.join(ksu_dir, 'kernel', 'infra', 'event_queue.h')
    if os.path.exists(eq_h):
        with open(eq_h, 'r', encoding='utf-8') as f:
            eq = f.read()
        if '#include <uapi/linux/eventpoll.h>' not in eq:
            eq = eq.replace('#include <linux/poll.h>', '#include <linux/poll.h>\n#include <uapi/linux/eventpoll.h>\n#ifndef __poll_t\ntypedef unsigned int __poll_t;\n#endif')
            with open(eq_h, 'w', encoding='utf-8') as f:
                f.write(eq)
            print("[+] Patched event_queue.h for __poll_t and eventpoll.h")

    # 11. Patch seccomp_cache.c for Linux 4.14 (no seccomp bitmap cache in < 5.10)
    sc_c = os.path.join(ksu_dir, 'kernel', 'infra', 'seccomp_cache.c')
    if os.path.exists(sc_c):
        with open(sc_c, 'r', encoding='utf-8') as f:
            scc = f.read()
        if 'SECCOMP_NO_OP_414' not in scc:
            shim = '''#include <linux/version.h>
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 10, 0)
// SECCOMP_NO_OP_414
#include <linux/fs.h>
struct seccomp_filter;
void ksu_seccomp_clear_cache(struct seccomp_filter *filter, int nr) {}
void ksu_seccomp_allow_cache(struct seccomp_filter *filter, int nr) {}
#else
'''
            scc = shim + scc + '\n#endif\n'
            with open(sc_c, 'w', encoding='utf-8') as f:
                f.write(scc)
            print("[+] Patched seccomp_cache.c for Linux 4.14")

    # 12. Patch arch.h for Linux 4.14 arm64 syscall symbol names
    arch_h = os.path.join(ksu_dir, 'kernel', 'include', 'arch.h')
    if os.path.exists(arch_h):
        with open(arch_h, 'r', encoding='utf-8') as f:
            ah = f.read()
        target_arch = """#define REBOOT_SYMBOL "__arm64_sys_reboot"
#define SYS_READ_SYMBOL "__arm64_sys_read"
#define SYS_EXECVE_SYMBOL "__arm64_sys_execve"
// https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/scripts/syscalltbl.sh;l=57;drc=9142be9e6443fd641ca37f820efe00d9cd890eb1
// https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/scripts/syscall.tbl;l=104;drc=b36d4b6aa88ef039647228b98c59a875e92f8c8e
#define SYS_FSTAT_SYMBOL "__arm64_sys_newfstat\""""
        repl_arch = """#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 19, 0)
#define REBOOT_SYMBOL "__arm64_sys_reboot"
#define SYS_READ_SYMBOL "__arm64_sys_read"
#define SYS_EXECVE_SYMBOL "__arm64_sys_execve"
#define SYS_FSTAT_SYMBOL "__arm64_sys_newfstat"
#else
#define REBOOT_SYMBOL "sys_reboot"
#define SYS_READ_SYMBOL "sys_read"
#define SYS_EXECVE_SYMBOL "sys_execve"
#define SYS_FSTAT_SYMBOL "sys_newfstat"
#endif"""
        if target_arch in ah:
            ah = ah.replace(target_arch, repl_arch)
            with open(arch_h, 'w', encoding='utf-8') as f:
                f.write(ah)
            print("[+] Patched arch.h for Linux 4.14 syscall symbols")

    # 13. Patch syscall_hook.c for sys_ni_syscall fallback
    sh_c = os.path.join(ksu_dir, 'kernel', 'hook', 'arm64', 'syscall_hook.c')
    if os.path.exists(sh_c):
        with open(sh_c, 'r', encoding='utf-8') as f:
            sh = f.read()
        target_sh = 'ni_syscall = (unsigned long)ksu_resolve_symbol_for_functable_hook("__arm64_sys_ni_syscall");'
        repl_sh = '''ni_syscall = (unsigned long)ksu_resolve_symbol_for_functable_hook("__arm64_sys_ni_syscall");
    if (!ni_syscall)
        ni_syscall = (unsigned long)ksu_resolve_symbol_for_functable_hook("sys_ni_syscall");'''
        if target_sh in sh:
            sh = sh.replace(target_sh, repl_sh)
            with open(sh_c, 'w', encoding='utf-8') as f:
                f.write(sh)
            print("[+] Patched syscall_hook.c for sys_ni_syscall fallback")

    # 14. Patch util.h for Linux 4.14 syscall prefix
    util_h = os.path.join(ksu_dir, 'kernel', 'include', 'util.h')
    if os.path.exists(util_h):
        with open(util_h, 'r', encoding='utf-8') as f:
            uh = f.read()
        target_uh = '#define KSU_SYS_PREFIX(name) __arm64_sys_##name'
        repl_uh = '''#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 19, 0)
#define KSU_SYS_PREFIX(name) __arm64_sys_##name
#else
#define KSU_SYS_PREFIX(name) sys_##name
#endif'''
        if target_uh in uh:
            uh = uh.replace(target_uh, repl_uh)
            with open(util_h, 'w', encoding='utf-8') as f:
                f.write(uh)
            print("[+] Patched util.h for Linux 4.14 KSU_SYS_PREFIX")

    # 15. Patch kpm.c for sys_truncate fallback
    kpm_c = os.path.join(ksu_dir, 'kernel', 'extension', 'kpm', 'kpm.c')
    if os.path.exists(kpm_c):
        with open(kpm_c, 'r', encoding='utf-8') as f:
            kc = f.read()
        target_kc = 'if (!fn) fn = (handler_t)find_kernel_symbol_exact("__arm64_sys_truncate.cfi");'
        repl_kc = '''if (!fn) fn = (handler_t)find_kernel_symbol_exact("__arm64_sys_truncate.cfi");
        if (!fn) fn = (handler_t)find_kernel_symbol_exact("sys_truncate");
        if (!fn) fn = (handler_t)find_kernel_symbol_exact("sys_truncate.cfi_jt");
        if (!fn) fn = (handler_t)find_kernel_symbol_exact("sys_truncate.cfi");'''
        if target_kc in kc:
            kc = kc.replace(target_kc, repl_kc)
            with open(kpm_c, 'w', encoding='utf-8') as f:
                f.write(kc)
            print("[+] Patched kpm.c for sys_truncate fallback")

    print("[+] All SukiSU 4.14 patches applied successfully!")

if __name__ == '__main__':
    patch()
