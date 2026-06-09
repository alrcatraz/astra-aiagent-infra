# 凭证管理规范

## 原则

1. **不存进仓库** — 凭证永远不进 Git，`registry.yaml` 不包含任何敏感信息
2. **分组管理** — 按性质分为 personal / work / other / temporary 四组，分开加密
3. **GPG 加密** — 凭证文件使用 `gpg --symmetric` 加密存储：`*.yaml.gpg`
4. **不落地明文** — 使用 `gpg -d` 管道解密，不在磁盘留下明文副本

## 参考

各组件应在各自的 README 中说明需要哪些凭证、如何设置环境变量。
