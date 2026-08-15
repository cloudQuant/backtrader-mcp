# 安全模型

## 边界

- stdio 只把协议帧写入 stdout；候选进程的 stdout/stderr 被重定向到按作业私有
  的日志文件。
- source、target、draft、CAS 与作业路径都被限定；符号链接与父目录穿越在调用
  方控制的边界处被拒绝。
- 校验与 change/run 令牌使用随机 256 位本地密钥、随机 nonce、过期时间与对
  规范哈希绑定的 HMAC-SHA256。nonce 一次性使用，在授权落地点（apply/start）
  于持久结果存在之后原子消费。
- apply 授权只来自可信本地 CLI 记录；审批审计携带审批者的 OS 身份。

## 审批的宿主假设

change/run 审批只由可信本地 CLI 创建，但"人机分离"只在宿主**不给** Agent
本地命令执行能力时成立：有 shell 权限的 Agent 可以自行运行打印出来的
`approve` 命令。需要更强隔离时，请把 `approve` CLI 置于 sudo/另一 OS 账户或
Agent 触达范围之外的审批守护进程之后。

## 候选执行

- 候选代码绝不被 MCP 进程导入。worker 用固定解释器、固定入口、最小环境、
  独立进程组、超时、捕获输出与已校验的结果契约启动它（adapter 类名与 feed
  名必须是 identifier；extra 指标名在 Markdown 中会被转义）。
- 进程控制在 POSIX 上使用独立 session 与 resource-limit pre-exec hook；非
  POSIX 启动省略这两个参数，可用时使用 Windows 进程组。锁层在 Windows 上
  回退到 `msvcrt` 字节范围锁。真实 Windows 宿主运行仍未记录。
- watchdog 清理只记录 PID 而不绑定进程启动时间；长期运行的宿主上被复用的
  PID 理论上可能被误发信号——心跳失速判定是主要防线。

## 已声明的残余风险

静态 AST 策略加子进程并不是 OS 沙箱：经审查的候选代码仍以本地用户的文件系统
权限运行。SQLite 状态是单主机的；带日志的目录交换可崩溃恢复，但不是分布式
事务。取消是基于进程的，不是 MCP Tasks 能力。对恶意代码请在容器或受限 OS
账户中运行本产品。
