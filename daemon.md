---
title: linux守护进程c++实现
date: 2019/10/02 11:23:58
tags: 
	- daemon
	- linux
	- c++
	- fork
	- nginx
	- redis
	- session
categories:
	- c++
comments: 
---

# Linux 进程
Linux 上值得关注的几种进程分别是：

+ 孤儿进程
+ 僵尸进程
+ 守护进程

孤儿进程是指子进程还在运行的时候，其父进程退出了，此时该子进程就变成 "孤儿进程"，孤儿进程会被 1 号 init(systemd) 进程收养，后续该子进程的退出清理工作就交由 init 进程来管理。

僵尸进程是指父进程 fork 了子进程后，子进程运行完毕退出，但父进程并没有使用 wait 或者 waitpid 来获取子进程的状态信息，导致子进程的进程描述符依然存在系统中，如果使用 ps 、top 等命令会看到进程状态为 Z，这种进程就是僵尸进程。僵尸进程有危害，如果大量产生僵尸进程，会大量消耗系统资源。

守护进程是指运行在后台的一种特殊进程，它脱离于控制终端，并且周期性地执行某种任务或等待处理某些发生的事件。linux 上大多数系统进程都是守护进程。

本文重点研究一下守护进程。

# 守护进程

先来看一个进程图：

```
 PPID   PID  PGID   SID TTY      TPGID STAT   UID   TIME COMMAND
    1  1162  1162  1162 ?           -1 Ss       0   0:00 /usr/sbin/sshd -D
 1162  1460  1460  1460 ?           -1 Ss       0   0:00  \_ sshd: root@pts/0
 1460  1464  1464  1464 pts/0     1507 Ss       0   0:00  |   \_ -bash
 1464  1506  1506  1464 pts/0     1507 S        0   0:00  |       \_ ./hello_world
 1464  1507  1507  1464 pts/0     1507 S+       0   0:00  |       \_ ./hello_world_fork
 1507  1508  1507  1464 pts/0     1507 S+       0   0:00  |           \_ ./hello_world_fork
 1507  1509  1507  1464 pts/0     1507 S+       0   0:00  |           \_ ./hello_world_fork
 1507  1510  1507  1464 pts/0     1507 S+       0   0:00  |           \_ ./hello_world_fork
 1507  1511  1507  1464 pts/0     1507 S+       0   0:00  |           \_ ./hello_world_fork
 
 1162  1479  1479  1479 ?           -1 Ss       0   0:00  \_ sshd: root@pts/1
 1479  1483  1483  1483 pts/1     1516 Ss       0   0:00  |   \_ -bash
 1483  1516  1516  1483 pts/1     1516 S+       0   0:00  |       \_ ./hello_world
 
 1162  1517  1517  1517 ?           -1 Ss       0   0:00  \_ sshd: root@pts/2
 1517  1521  1521  1521 pts/2     1536 Ss       0   0:00      \_ -bash
 1521  1536  1536  1521 pts/2     1536 R+       0   0:00          \_ ps ajxf

```

上面是使用  `ps ajxf` 命令的输出的其中一部分，只展示了终端相关的进程情况。可以看到这台机器上开了 3 个终端，每个终端上有不同的进程在运行。

接下来就以上面的结果为例作说明。
<!-- more -->


## 会话和进程组
会话也就是 session，每一个终端对应一个会话。当有新用户登录 shell 之后，可以把整个 shell 程序看成一个会话。会话随着终端用户登录而创建，随终端用户退出而终止。

一个会话可以包含多个进程，每个进程都属于一个进程组，父进程创建了子进程，它们就形成一个进程组，并且父进程成为进程组组长；采用进程组的目的是能够统一控制信号的分发，给一个进程组发送信号，信号会发送给进程组中的每一个进程。

+ PPID: 父进程 ID
+ PID: 进程 ID
+ PGID: 进程组 ID
+ SID: 会话 ID
+ TTY: shell 对应的虚拟终端，使用 `tty` 可以查看当前 shell 对应的虚拟终端（如上图，展示了 3 个终端）


## demo 验证
分别准备两个版本的程序员入门代码: 

> hello_world.cc

```
#include <iostream>
#include <unistd.h>

int main() {
    std::cout << "Hello world" << std::endl;
    while (true) {
        sleep(2);
    }
    return 0;
}
```

编译命令：

```
g++ hello_world.cc   -o hello_world
```

> hello_world_fork.cc

```
#include <iostream>
#include <unistd.h>

void child_work() {
    std::cout << "child "<< getpid() << " :Hello world" << std::endl;
    while (true) {
        sleep(2);
    }
}

void father_work() {
    pid_t pid = fork();
    if (pid == 0) {
        child_work();
        return;
    }

    pid = fork();
    if (pid == 0) {
        child_work();
        return;
    }

    pid = fork();
    if (pid == 0) {
        child_work();
        return;
    }

    pid = fork();
    if (pid == 0) {
        child_work();
        return;
    }


    while (true) {
        sleep(2);
    }
}


int main() {
    father_work();
    return 0;
}
```

编译命令：

```
g++ hello_world_fork.cc  -o hello_world_fork
```

上面的代码很简单，一个是直接打印 "hello world"，另外一个是 fork 了多个子进程打印 "hello world"。

分别启动 3 个终端，在第一个终端上执行：

```
./hello_world &
./hello_world_fork
```

在第二个终端上执行：

```
./hello_world
```

在第三个终端上进行查询：

```
ps ajxf
```

可以看到如下的结果：

```
 PPID   PID  PGID   SID TTY      TPGID STAT   UID   TIME COMMAND
    1  1162  1162  1162 ?           -1 Ss       0   0:00 /usr/sbin/sshd -D
 1162  1460  1460  1460 ?           -1 Ss       0   0:00  \_ sshd: root@pts/0
 1460  1464  1464  1464 pts/0     1507 Ss       0   0:00  |   \_ -bash
 1464  1506  1506  1464 pts/0     1507 S        0   0:00  |       \_ ./hello_world
 1464  1507  1507  1464 pts/0     1507 S+       0   0:00  |       \_ ./hello_world_fork
 1507  1508  1507  1464 pts/0     1507 S+       0   0:00  |           \_ ./hello_world_fork
 1507  1509  1507  1464 pts/0     1507 S+       0   0:00  |           \_ ./hello_world_fork
 1507  1510  1507  1464 pts/0     1507 S+       0   0:00  |           \_ ./hello_world_fork
 1507  1511  1507  1464 pts/0     1507 S+       0   0:00  |           \_ ./hello_world_fork
 
 1162  1479  1479  1479 ?           -1 Ss       0   0:00  \_ sshd: root@pts/1
 1479  1483  1483  1483 pts/1     1516 Ss       0   0:00  |   \_ -bash
 1483  1516  1516  1483 pts/1     1516 S+       0   0:00  |       \_ ./hello_world
 
 1162  1517  1517  1517 ?           -1 Ss       0   0:00  \_ sshd: root@pts/2
 1517  1521  1521  1521 pts/2     1536 Ss       0   0:00      \_ -bash
 1521  1536  1536  1521 pts/2     1536 R+       0   0:00          \_ ps ajxf

```

可以看到 3 个 shell 会话的会话 ID 分别是 1464、1483、1521，每一个 bash 进程是由 sshd 这个进程创建而来的，可以看到上面每个 bash 进程的父进程分别是 1460、1479、1517。

如果父进程创建了多个子进程，那么这些进程构成一个进程组，其父进程成为进程组组长，如上的 `hello_world_fork` 进程，可以看到他们的父进程是 1507，并且它们同属于一个进程组 1507。

上面还值得注意的是  `/usr/sbin/sshd -D` 这个进程，可以看到它的父进程 ID 是 1，并且 TTY 没有具体值，即没有控制终端，这个进程就是守护进程。


## c++ 实现守护进程

源码可以在我的 github 找到：

[https://github.com/smaugx/linux_daemon](https://github.com/smaugx/linux_daemon)


```
#include <cstdio>
#include <cstdlib>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/fcntl.h>


bool daemon() {
    int fd;

    switch (fork()) {
        case -1:
            // fork 出错，直接返回
            return false;
        case 0:
            // 第一个子进程
            break;
        default:
            // 父进程直接退出
            exit(0);
    }

    // setsid() 函数会创建一个新会话，目的是让上面创建的第一个子进程脱离控制终端和进程组，并让这个子进程成为会话组组长，与原来的登陆会话和进程组脱离
    // 到这，第一个子进程已经成为无终端的会话组组长，但是对于一个会话组组长来说，它依然能够重新申请打开一个控制终端
    if (setsid() == -1 ) {
        // setsid 失败，直接返回
        return false;
    }

    // 第二次 fork
    // 目的是为了让进程不再成为会话组长，避免它重新申请打开控制终端
    switch (fork()) {
        case -1:
            // fork 出错，直接返回
            return false;
        case 0:
            // 第二个子进程产生
            break;
        default:
            // 第一个子进程退出
            exit(0);
    }

    // 重新设置文件权限的掩码，目的是去除终端用户的默认文件、文件夹权限，比如 centos 普通用户 umask 为 0022，默认创建的文件权限为 644，文件夹权限为 755
    // 如果重新设置掩码 umask 为 0 的话，那么默认创建的文件权限就是 666，文件夹就是 777
    umask(0);


    // 守护进程不应该在终端有任何的输出，使用 dup2 函数把 stdin,stdout,stderr 重定向到 /dev/null
    fd = open("/dev/null", O_RDWR);
    if (fd == -1) {
        return false;
    }

    if (dup2(fd, STDIN_FILENO) == -1) {
        return false;
    }

    if (dup2(fd, STDOUT_FILENO) == -1) {
        return false;
    }

#if 0
    if (dup2(fd, STDERR_FILENO) == -1) {
        return;
    }
#endif

    if (fd > STDERR_FILENO) {
        if (close(fd) == -1) {
            return false;
        }
    }

    return true;
}

void do_work() {
    FILE *fp = fopen("/tmp/daemon.log", "w");
    if (!fp) {
        return;
    }
    while (true) {
        fprintf(fp, "ABCDEDFGH\n");
        fflush(fp);
        sleep(10);
    }
    fclose(fp);
}


int main() {

    if (!daemon()) {
        return -1;
    }

    do_work();

    return 0;
}
```

上面的代码注释其实已经很详细了，这里单独再说两点：

> 两次 fork 的问题

第二次 fork 的目的是为了让第一次 fork 产生的第一个子进程不再成为新会话的会话组长，避免它再次申请控制终端；如果能够确保第一次 fork 之后不会有控制终端的申请，那么第二次 fork 不是必须的。比如 nginx、redis 都是只有一次 fork.

> umask(0)

重设文件权限掩码。每一个用户都有默认的文件权限，可以执行 `umask` 命令查看当前用户的文件权限掩码。

```
# umask
0022
```

文件默认最高权限为 666，也就是 `-rw-rw-rw-`，文件夹默认最高权限为 777，也就是 `drwxrwxrwx`，如果 umask 为 `0022` ，那么该用户创建的文件以及文件夹的权限分别为 644 和 755。重设文件权限掩码为 `0000` 的目的就在此，确保守护进程的文件操作权限为最高。


# The END
守护进程的应用场景很广泛，尤其是一些保活的场景会经常用得到。




Blog:
 
+ [rebootcat.com](http://rebootcat.com)

+ email: <linuxcode2niki@gmail.com>

2019-10-02 于杭州   
*By  [史矛革](https://github.com/smaugx)*