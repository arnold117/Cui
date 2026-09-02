# 契约测试(contracts)

两层,服务于 spec S15(kernel 纯度机器执法)+ plan T4:

1. **方向断言(层间 import 规则)** —— 真身是 `backend/linter/contracts.py`(单一真相源),
   运行方式:`make lint-contracts`(或 `cd backend && python -m linter`)。它把声明的
   源包展开成具体模块喂给 import-linter 执行。**新契约加这里**,不要绕过 gate。

2. **接口签名快照** —— 本目录的 `test_*.py`:对跨层关键接口(协议/服务)断言其公开形状
   (方法集合、字段集合),防止改名/删接口在无调用方时悄悄溜过。规则:
   - 一个文件只快照一个接口;文件头注释写明为什么这个接口值得钉住(跨层边界)。
   - 断言"契约最小集"(接口必须有这些成员),不要枚举实现细节;接口演进时先改实现
     再改快照,并在 commit 说明里写明破坏性变更。

示例:`test_native_store_interface.py`(kernel `NativeEventStore` 协议 = SDK/服务依赖
的持久化边界)。

验收线(plan T4):`make lint-contracts` 0 违规;故意引入的方向性错误会让 gate 变红
(负例验证方式:临时在某 kernel 模块加 `from cui.llm.client import ...`,跑 gate 应 FAIL,
删掉恢复)。
