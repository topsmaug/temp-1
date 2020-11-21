---
title: fork会复制线程吗
date: 2020/11/21 11:23:58
tags: 
	- fork
	- linux
	- c++
	- thread
categories:
	- c++
comments: 
---

# 诡异的死锁
事情是这样的，观察到某台机器上出现了卡死的现象，即没有刷新日志，cpu 使用也较低，怀疑是不是出现了死锁。

由于程序采用的是 `master + worker` 的模式，首先 gdb attach 观察 master 情况，发现 master 执行正常，没有 **lock wait** 相关的堆栈；然后 gdb attach 观察 worker 情况，结果发现 worker 堆栈上有 **lock wait** 的情况，果然是出现了死锁，但 worker 上的其他线程并没有发现在等待锁的情况。

根据堆栈，找到 worker 的代码，重新梳理了一下代码，检查了 std::mutex 相关的函数调用，并没有出现嵌套调用的情况，也没有出现递归调用的情况，和上面发现 worker 其他线程没有等待锁的情况相吻合。

说明 worker 的死锁，并非由于 worker 内部的多线程造成的。那么就很诡异了，不是 worker 内部死锁，难道是多进程死锁？


# 排查验证
重新又检查了 worker 各个线程的堆栈情况，发现确实只有一个线程出现 **lock wait** 相关的堆栈； 并且又检查了一下 master 进程内部的各个线程，堆栈也都正常。

那 worker 锁住的这个线程，到底是因为什么原因？梳理 worker 代码，找到 std::mutex 相关的函数调用，发现 master 调用的一个函数使用到了 std::mutex，但是该函数内部逻辑也较为简单，不会一直占用这把锁。

没有头绪，谷歌搜索了一些类似的问题，找到了一点端倪。**主进程 fork 之后，仅会复制发起调用的线程，不会复制其他线程，如果某个线程占用了某个锁，但是到了子进程，该线程是蒸发掉的，子进程会拷贝这把锁，但是不知道谁能释放，最终死锁**。

确实符合这个程序的行为，并且确实是多进程下子进程的死锁，而且找不到其他线程也在等待锁。

接下来，写一个 demo 验证一下，是否 fork 不会复制子线程，并且有可能造成死锁。

## fork demo 验证

简单写一个 demo:

<!-- more -->

```
// file: fork_copy_thread.cc
// g++ fork_copy_thread.cc  -o fork_copy_thread -std=c++11 -lpthread -ggdb


#include <cstdio>
#include <unistd.h>

#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <chrono>
#include <mutex>

class Event {
public:
    Event() = default;
    ~Event() = default;
public:
    std::string str_;
};


class TaskHandler {
public:
    TaskHandler() = default;
    ~TaskHandler() = default;

public:
    void start() {
        auto lam = [&]() -> void {
            {
                std::unique_lock<std::mutex> lock(ev_mutex_);
                this->ev_ = std::make_shared<Event>();
                this->ev_->str_ = "hello fork";
                // hold this lock for 10 seconds
                std::this_thread::sleep_for(std::chrono::seconds(10));
            }
            std::cout << "father thread done, exit" << std::endl;
        };

        std::thread th(lam);
        th.detach();
    }

    void print_str() {
        std::unique_lock<std::mutex> lock(ev_mutex_);
        if (!ev_) {
            std::cout << "event  not ready" << std::endl;
            return;
        }
        std::cout << "event:" << ev_->str_ << std::endl;
    }

private:
    std::shared_ptr<Event> ev_ { nullptr };
    std::mutex ev_mutex_;
};

std::shared_ptr<TaskHandler> tsk = nullptr;

int main() {
    tsk = std::make_shared<TaskHandler>();
    tsk->start();
    std::this_thread::sleep_for(std::chrono::seconds(1));

    // for child process
    pid_t pid = fork();
    switch (pid) {
        case -1:
            {
                return -1;
            }
        case 0:
            {
                std::cout << "this is child process" << std::endl;
                while (true) {
                    // will core here, because tsk->ev_ is created in father-thread, not copyed,
                    // so in child process, tsk->ev_ is nullptr
                    tsk->print_str();
                    std::this_thread::sleep_for(std::chrono::seconds(1));
                }
            }
        default:
            {
                // this is father
                break;
            }
    } // end switch

    while (true) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    return 0;
}
```


上面的代码简单解释一下：

+ TaskHandler::start() 中会创建一个线程，线程会申请一把互斥锁，并且睡眠 10s，目的是为了在 fork 的时候依然占用这把互斥锁
+ TaskHandler::print_str() 会申请这把互斥锁，然后打印字符串
+ 程序 main 开始，调用 start() 创建子线程
+ 然后 fork() 子进程
+ 子进程死循环执行 print_str() 函数打印字符串


使用编译命令：

```
$ g++ fork_copy_thread.cc  -o fork_copy_thread -std=c++11 -lpthread -ggdb
```

运行后与预期不符，子进程并没有死循环打印字符串，死锁了。

然后使用 gdb attach 子进程：

```
(gdb) bt
#0  0x00007f4154e1a54d in __lll_lock_wait () from /lib64/libpthread.so.0
#1  0x00007f4154e15e9b in _L_lock_883 () from /lib64/libpthread.so.0
#2  0x00007f4154e15d68 in pthread_mutex_lock () from /lib64/libpthread.so.0
#3  0x000000000040128c in __gthread_mutex_lock (__mutex=0x1d2fc48) at /usr/include/c++/4.8.5/x86_64-unknown-linux-gnu/bits/gthr-default.h:748
#4  0x0000000000401730 in std::mutex::lock (this=0x1d2fc48) at /usr/include/c++/4.8.5/mutex:134
#5  0x0000000000401f99 in std::unique_lock<std::mutex>::lock (this=0x7fff168c43a0) at /usr/include/c++/4.8.5/mutex:511
#6  0x0000000000401b13 in std::unique_lock<std::mutex>::unique_lock (this=0x7fff168c43a0, __m=...) at /usr/include/c++/4.8.5/mutex:443
#7  0x0000000000401988 in TaskHandler::print_str (this=0x1d2fc38) at fork_copy_thread.cc:43
#8  0x00000000004013ff in main () at fork_copy_thread.cc:76
(gdb)
```

果然可以看到子进程卡在了 print_str() 函数上。

上面的代码，父进程创建线程后，占用了锁，此时 fork 了子进程，子进程拷贝了父进程空间的内存，包括锁，但是没有复制子线程，造成子进程无法获取锁，最终死锁。

## fork copy thread?
上面已经验证了死锁的产生原因是由于 fork 时并没有把父进程里的线程复制到子进程，导致子进程无法获取锁。那么简单修改一下上面的代码，来验证一下子进程确实是没有复制父进程的子线程。

```
// file: fork_copy_thread.cc
// g++ fork_copy_thread.cc  -o fork_copy_thread -std=c++11 -lpthread -ggdb


#include <cstdio>
#include <unistd.h>

#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <chrono>
#include <mutex>

class Event {
public:
    Event() = default;
    ~Event() = default;
public:
    std::string str_;
};


class TaskHandler {
public:
    TaskHandler() = default;
    ~TaskHandler() = default;

public:
    void start() {
        auto lam = [&]() -> void {
            {
                std::unique_lock<std::mutex> lock(ev_mutex_);
                this->ev_ = std::make_shared<Event>();
                this->ev_->str_ = "hello fork";
                // hold this lock for 10 seconds
                //std::this_thread::sleep_for(std::chrono::seconds(10));
            }
            while (true) {
                std::cout << "this threadid:" << std::this_thread::get_id() << " run" << std::endl;
                std::this_thread::sleep_for(std::chrono::seconds(1));
            }
        };

        std::thread th(lam);
        th.detach();
    }

    void print_str() {
        std::unique_lock<std::mutex> lock(ev_mutex_);
        if (!ev_) {
            std::cout << "event  not ready" << std::endl;
            return;
        }

        std::cout << "event:" << ev_->str_ << std::endl;

    }

private:
    std::shared_ptr<Event> ev_ { nullptr };
    std::mutex ev_mutex_;
};

std::shared_ptr<TaskHandler> tsk = nullptr;

int main() {
    tsk = std::make_shared<TaskHandler>();
    tsk->start();
    std::this_thread::sleep_for(std::chrono::seconds(1));

    // for child process
    pid_t pid = fork();
    switch (pid) {
        case -1:
            {
                return -1;
            }
        case 0:
            {
                std::cout << "this is child process" << std::endl;
                while (true) {
                    // will core here, because tsk->ev_ is created in father-thread, not copyed,
                    // so in child process, tsk->ev_ is nullptr
                    //tsk->print_str();
                    std::this_thread::sleep_for(std::chrono::seconds(1));
                }
            }
        default:
            {
                // this is father
                break;
            }
    } // end switch

    while (true) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    return 0;
}
```

简单解释一下修改了啥：

+ 父进程启动一个线程，循环打印字符串
+ 父进程 fork，子进程保持睡眠
+ 验证子进程是否有线程打印字符串(如果复制了的话，理应会打印）


执行结果：

```
$ ./fork_copy_thread
this threadid:139674369169152 run
this threadid:139674369169152 run
this is child process
this threadid:139674369169152 run
this threadid:139674369169152 run
this threadid:139674369169152 run
```

可以看到只有一个线程在打印，也就是父进程创建的那个线程；fork 之后父进程的线程在子进程蒸发了。

**多线程程序使用 fork 一定要谨慎，再谨慎，并且也不推荐这样的做法。**

# fork 到底复制了什么

> [https://linux.die.net/man/3/fork](https://linux.die.net/man/3/fork)

```
#include <unistd.h>

pid_t fork(void);

```

## Copy On Write
> Copy On Write(写时复制）技术大大提高了 fork 的性能。fork 之后，内核会把父进程中的所有内存页都设置为 read-only，然后子进程的地址空间指向父进程。如果父进程和子进程都没有涉及到内存的写操作，那么父子进程保持这样的状态，也就是子进程并不会复制父进程的内存空间；如果父进程或者子进程产生了写操作，那么由于内存页被设置为 read-only，所以会触发页异常中断，然后中断程序会把该内存页复制一份，至此父子进程就拥有不同的内存页；而其他没有操作的内存页依然共享。

上面这段话不太好理解，涉及到的东西其实比较深也比较多。我们把它拆开来说。

**虚拟内存空间**，进程是看不见物理内存地址的，进程的内存空间称为虚拟内存，默认从 0 到 max，虚拟内存空间也就是逻辑内存地址，进程操作的都是逻辑内存地址。

虚拟内存地址到真实的物理内存地址的转换或者映射称为**地址重定向**，有专门的中断程序来负责处理，作为进程本身不需要关心。

**物理内存的单位是页，也就是内核使用页为单位来管理物理内存**，数据结构上页其实是一个 struct，大小好像是 4KB。虚拟内存地址映射到物理内存以页的方式进行，并且**内核管理一个页映射表**。

**malloc 分配内存，其实操作的是虚拟内存**，也即使用 malloc 分配了一段内存后，在未赋值之前，其实是没有物理内存占用的，当真正向 malloc 分配的内存写数据的时候，内核才会分配真实的物理内存页，并让这段虚拟内存指向实际的物理内存页。并且进程管理一个页表。


进程的虚拟内存空间，由地地址到高地址空间大致分为代码段、数据段、BSS 段、堆、栈，详情如下：

![](https://cdn.jsdelivr.net/gh/smaugx/MyblogImgHosting_2/rebootcat/free_memory/1.png)

fork 之后，子进程复制了父进程的虚拟内存空间，即复制了代码段、堆栈等，所以变量的地址也是一样的。并且父子进程各自有一份页映射表，它们都指向父进程的物理内存地址。

当父子进程只读时，不会发生真实的物理内存拷贝；但是当父子进程写入时，由于物理页 read-only，会触发页异常中断，中断程序会把该页面复制一份，其他的页保持不动。至此父进程和子进程的页映射表就出现了一点不一致了，但其他部分还是一致的。

## 简单总结下 fork
要理解 fork 的原理，Copy On Write 的原理，重点是理解虚拟内存和物理内存的关系。

fork 之后，**子进程会复制父进程的虚拟内存空间，也就是代码段、数据段、堆栈等，虚拟内存空间里表达的就是程序里各个变量的地址，所以子进程里各个变量的地址和父进程里各个变量的地址是一样的**。

**父子进程只读时，不会发生真实的物理内存拷贝，他们的页映射表内容一致，即同样的虚拟内存地址指向同样的物理内存地址；但当有一方写入数据时，内核会复制要写入的页，此时修改数据的一方的页映射表就发生了变化，即同样的虚拟内存地址指向了不同的物理内存地址，但其他部分还是一样的**；

另外，**fork 仅会将发起调用的线程复制到子进程中，所以子进程中的线程 ID 与主进程线程 ID 有一致的情况。其他线程不会被复制**。


# The End

关于 fork 的细节，还有很多值得深入研究的东西。


Blog:
 
+ [rebootcat.com](http://rebootcat.com)

+ email: <linuxcode2niki@gmail.com>

2020-11-21 于杭州   
*By  [史矛革](https://github.com/smaugx)*

