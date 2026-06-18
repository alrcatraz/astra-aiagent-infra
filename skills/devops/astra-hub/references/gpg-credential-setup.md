# GPG 基础设施凭证设置流程

> 适用于新机器/新 Hermes 实例首次配置凭证存储。
> 更新日期: 2026-06-09（从单文件迁移为四分组 YAML schema）

## 前置条件

- NAS (ds425plus) 可达，GPG 密钥备份在 Utopia/GPG/GPG_Cert/
- GPG 已安装
- Alrcatraz 私钥密码已在 `.env` 中（`GPG_Key_Alrcatraz`）

## 凭证分组架构

凭证按四组独立文件存储，均用 `Alrcatraz <alrcatraz@gmx.com>` 密钥 GPG 加密：

| 分组 | 文件 | 内容 |
|:----|:-----|:-----|
| 🔵 个人 | `personal-credentials.yaml.gpg` | 自有设备（SUSET01、DS425Plus、VPS 等） |
| 🟠 工作 | `work-credentials.yaml.gpg` | 客户/工作服务器 |
| 🟢 其他 | `other-credentials.yaml.gpg` | 朋友/家人/共享设备 |
| ⚪ 临时 | 不持久化 | 一次性访问，用完即弃 |

## 从 NAS 获取私钥

```bash
ssh ds425plus 'cat "/volume1/homes/Alrcatraz/Utopia/GPG/GPG_Cert/private_backup/Alrcatraz_SECRET.asc"' \
  > /tmp/Alrcatraz_SECRET.asc
```

## 导入私钥

```bash
source <(grep 'GPG_Key_Alrcatraz' ~/.hermes/.env)
echo "$GPG_Key_Alrcatraz" | gpg --batch --passphrase-fd 0 --import /tmp/Alrcatraz_SECRET.asc
```

## 设置信任等级

```bash
echo -e "5\ny\n" | gpg --batch --command-fd 0 --edit-key B01ECDF27D2D156D trust
```

## YAML Schema 参考

详见 `~/Documents/credentials/` 中的 `.yaml.gpg` 文件。统一结构：

```yaml
devices:
  <identifier>:
    hostname: "<hostname>"
    os:
      name: "<发行版名>"
    description: "<用途>"
    tags:
      - <分组>
      - <设备类型>
    network:
      main_ip: "<主IP>"
      overlay:
        easy_tier: "<IP>"
        zero_tier: "<IP>"
        tailscale: "<IP>"
    connection:
      paths:
        - priority: 1
          type: "direct"
          via: []
        - priority: 2
          type: "jump"
          via:
            - host: "<跳板>"
              user: "<用户>"
              ip: "<IP>"
    access:
      methods:
        - type: ssh_key
          key_path: "~/.ssh/id_xxx"
        - type: password
          value: "<密码>"
    accounts:
      - username: "<用户>"
        is_admin: true
        access: sudo
    services:
      - name: "<服务>"
        type: web_ui
        accounts:
          - username: "<用户>"
            password: "<密码>"
```

## 加密新文件

```bash
source <(grep 'GPG_Key_Alrcatraz' ~/.hermes/.env)
cat /tmp/my-credentials.yaml | gpg --batch --yes --symmetric \
  --passphrase "$GPG_Key_Alrcatraz" --cipher-algo AES256 \
  --output ~/Documents/credentials/personal-credentials.yaml.gpg
rm /tmp/my-credentials.yaml
```

## 解密验证

```bash
source <(grep 'GPG_Key_Alrcatraz' ~/.hermes/.env)
echo "$GPG_Key_Alrcatraz" | gpg --batch --no-tty --passphrase-fd 0 \
  --pinentry-mode loopback \
  --decrypt ~/Documents/credentials/personal-credentials.yaml.gpg 2>/dev/null
```

## 安全要点

- GPG 密码存 `.env`（`GPG_Key_Alrcatraz`），不进记忆、不进 skill 文本
- SSH key 优先于密码；密码仅在 key 不可用时降级回退
- 临时凭证用完即弃，不持久化
- 记忆里存 `→GPG creds` 引用，不存实际值
- 旧单文件 `infra-credentials.yaml.gpg.deprecated` 已废弃
