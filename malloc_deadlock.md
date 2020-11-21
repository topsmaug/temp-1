---
title: malloc 死锁
date: 2020/05/25 11:23:58
tags: 
	- malloc
	- signal
	- deadlock
categories:
	- c++
comments: 
---

# 缘由
xxnode 是一个程序，执行 `xxnode -v` 出现卡住不动的情况。

正常情况下，`xxnode -v` 会打印出程序版本号等信息，而且只是简单的打印版本号就会推出，不涉及到复杂的业务逻辑，但本次碰到的情况是卡住不动了，马上怀疑肯定是出现死锁了。

# 排查死锁
```
$ ps -ef |grep xxnode
8987
```
上面先找到卡住的 xxnode 的进程号，然后使用 gdb attach 上去：

```
$ gdb attach 8987
```

然后使用 `bt` 查看堆栈情况，发现堆栈如下：

```
(gdb) bt
#0  0x00007f9d320df5cc in __lll_lock_wait_private () from /lib64/libc.so.6
#1  0x00007f9d3205bb12 in _L_lock_16654 () from /lib64/libc.so.6
#2  0x00007f9d32058753 in malloc () from /lib64/libc.so.6
#3  0x00007f9d32917ecd in operator new(unsigned long) () from /lib64/libstdc++.so.6
#4  0x00007f9d32976a19 in std::string::_Rep::_S_create(unsigned long, unsigned long, std::allocator<char> const&) () from /lib64/libstdc++.so.6
#5  0x00007f9d3297762b in std::string::_Rep::_M_clone(std::allocator<char> const&, unsigned long) () from /lib64/libstdc++.so.6
#6  0x00007f9d329776d4 in std::string::reserve(unsigned long) () from /lib64/libstdc++.so.6
#7  0x00007f9d3297793f in std::string::append(char const*, unsigned long) () from /lib64/libstdc++.so.6
#8  0x0000000001431d8d in xwrite_log2 (module=0x14d4c14 "xnetwork", file=0x14d7a0b "xmain.cpp", function=0x14db0c0 <get_child_status()::__FUNCTION__> "get_child_status", line=1865, 
    level=enum_xlog_level_warn, msg=0x14d8a4e "waitpid() failed: ECHILD") at ../../src/xlog.cpp:717
#9  0x0000000000dc4fd5 in get_child_status () at /home/xchano/src/xtopcom/xnode/src/xmain.cpp:1865
#10 0x0000000000dc490f in signal_handler (signo=17) at /home/xchano/src/xtopcom/xnode/src/xmain.cpp:1763
#11 0x0000000000dc4cc8 in xnode_signal_handler (signo=17, siginfo=0x7fffdc448f70, ucontext=0x7fffdc448e40) at /home/xchano/src/xtopcom/xnode/src/xmain.cpp:1798
#12 <signal handler called>
#13 0x00007f9d32054f41 in _int_malloc () from /lib64/libc.so.6
#14 0x00007f9d320586fc in malloc () from /lib64/libc.so.6
#15 0x00007f9d32917ecd in operator new(unsigned long) () from /lib64/libstdc++.so.6
#16 0x00007f9d32976a19 in std::string::_Rep::_S_create(unsigned long, unsigned long, std::allocator<char> const&) () from /lib64/libstdc++.so.6
#17 0x00000000013e9df1 in char* std::string::_S_construct<char const*>(char const*, char const*, std::allocator<char> const&, std::forward_iterator_tag) ()
#18 0x00007f9d329786d8 in std::basic_string<char, std::char_traits<char>, std::allocator<char> >::basic_string(char const*, std::allocator<char> const&) () from /lib64/libstdc++.so.6
#19 0x00007f9d2fe2d5fa in top::get_md5 () at /home/xchano/src/programs/xtopchano/src/version.cpp:31
#20 0x00007f9d2fe2dc23 in top::print_version () at /home/xchano/src/programs/xtopchano/src/version.cpp:62
#21 0x00007f9d2fe2d24e in init_noparams_component (component_name=0x7f9d32bbf338 <std::string::_Rep::_S_empty_rep_storage+24> "", 
    pub_key=0x26532c8 "BEANYyQhGD0urjcRfsmqJLctMA5Hpe6DHW4pb6Asm50o/FgY2iU82bamk0WM0GtQXhNQykvy60DMmCHVWGhFR2c=", pub_len=88, 
    pri_key=0x2656858 "Lv1qWftE/8rQfMxufh+5ywy0maCdWl2ikdNun4wVjAM=", pri_len=44, node_id=0x2653378 "T-0-LWT5UjpGiSPzWs7Gt3Fc8ZmNFFwwA7Gpmt", datadir=0x26517a8 "/chano", 
    config_file_extra=0x26519e8 "/chano/extra_conf.json") at /home/xchano/src/programs/xtopchano/so.cpp:18
#22 0x0000000000dba3b5 in lib_load (cmd_type=0, config=...) at /home/xchano/src/xtopcom/xnode/src/xmain.cpp:176
#23 0x0000000000dc45c0 in child_load_so (cmd_type=0, config=...) at /home/xchano/src/xtopcom/xnode/src/xmain.cpp:1666
#24 0x0000000000dc4349 in spawn_child (cmd_type=0, config=...) at /home/xchano/src/xtopcom/xnode/src/xmain.cpp:1611
#25 0x0000000000dc8897 in xnode_master_process_cycle (cmd_type=0, config=...) at /home/xchano/src/xtopcom/xnode/src/xmain.cpp:2244
#26 0x0000000000dc092c in main (argc=7, argv=0x7fffdc44bce8) at /home/xchano/src/xtopcom/xnode/src/xmain.cpp:1155
(gdb) b version.cpp:31
Breakpoint 1 at 0x7f9d2fe2d5d4: file /home/xchano/src/programs/xtopchano/src/version.cpp, line 31.
```

注意看上面的第 2 帧和第 14 帧，都出现了 malloc 函数的调用，而 glibc malloc 内部的实现是有锁的，所以果然是出现了死锁。

上面的执行流程是这样的：

1. 主进程启动
2. fork 子进程，子进程会 load 一个 libxxxnode.so
3. 子进程调用 so 里提供的 `print_version()` 函数，打印版本信息
4. `print_version()` 函数内部有 string 的操作，也就是说会产生  malloc 的调用，正当在 malloc 内部的时候，不知道什么原因触发了某个信号（上面 signo=17）
5. 程序执行转移到 `signal_handler()`，处理信号
6. 但是不巧， `signal_handler()` 内部操作了日志，也就是也会调用到 malloc 函数
7. 然后陷入死锁


所以，**问题出现在了 `signal_handler()` 上，该信号处理函数调用了 malloc，而 malloc 是不可重入函数，造成最终的死锁**。

# 解决
要解决该死锁问题当然也简单，就是确保信号处理函数 `signal_handler()` 是可重入函数即可，这样即便在发生上面的场景，也就不会陷入死锁当中。



Blog:
 
+ [rebootcat.com](http://rebootcat.com)

+ email: <linuxcode2niki@gmail.com>

2020-05-25 于杭州   
*By  [史矛革](https://github.com/smaugx)*

