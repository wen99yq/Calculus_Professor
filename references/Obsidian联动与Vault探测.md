# Obsidian 联动与 Vault 探测

> 本能力**内置于 `Calculus_Professor` 自身**，不依赖外部 `obsidian` skill 是否安装。
> 目标：在 Windows / macOS / Linux 上自动找到学生的 Obsidian 库；找不到就优雅回退。

---

## 一、探测优先级

按顺序尝试，**第一个命中即采用**：

| 顺序 | 来源 | 说明 |
|---|---|---|
| 1 | `config.json` 的 `vault_path` | 学生手动指定过就用它（最高优先级，最可靠） |
| 2 | 环境变量 `CALCULUS_VAULT` | 便于高级用户或批量部署 |
| 3 | 系统 `obsidian.json` | Obsidian 官方记录库清单的位置，取 `"open": true` 的条目 |
| 4 | 回退 | 全部失败 → 笔记写入 `微积分学习/笔记/`，并询问学生路径 |

### ⚠️ 首次写入前必须确认（强制）

自动探测只能说明"**这是你最近打开过的库**"，不等于"**你想把微积分笔记写在这里**"。

学生可能有好几个库（课程笔记库、日记库、兴趣库…），当前打开的未必是合适的那个。

因此，**第一次**要把笔记写入某个探测到的 vault 时，必须先问一句并等待确认：

> 我在你电脑上找到 Obsidian 库：`D:\Obsidian\学习库`（你最近打开的）
> 微积分笔记我打算写到 `D:\Obsidian\学习库\微积分\`，可以吗？
> 如果你有专门放课程笔记的库，告诉我路径，我记下来以后就用那个。

- 学生**确认** → 调用 `find_vault.py --set "<路径>"` 写入 `config.json`，之后**不再重复询问**
- 学生**指定其他路径** → 用该路径写入 `config.json`
- 学生**说不出/不想用 Obsidian** → 走回退，写入 `微积分学习/笔记/`
- 已经确认过的库（`config.json` 里有记录）→ 直接使用，不再打扰

### 系统 `obsidian.json` 的跨平台位置

| 平台 | 路径 |
|---|---|
| Windows | `%APPDATA%\obsidian\obsidian.json` （即 `C:\Users\<用户>\AppData\Roaming\obsidian\obsidian.json`） |
| macOS | `~/Library/Application Support/obsidian/obsidian.json` |
| Linux | `~/.config/obsidian/obsidian.json`（兜底：`~/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json`，Flatpak 安装） |

`obsidian.json` 结构形如：

```json
{
  "vaults": {
    "a1b2c3d4e5f6a7b8": {
      "path": "D:\\MyVault",
      "ts": 1737000000000,
      "open": true
    },
    "ffeeddccbbaa9988": {
      "path": "C:\\Users\\Someone\\Documents\\AnotherVault",
      "ts": 1736900000000
    }
  }
}
```

- `path` 就是 vault 的**绝对路径**
- `"open": true` 表示当前打开的库 → **优先选它**
- 若有多个 `open: true`，取 `ts`（时间戳）最大的那个
- 若一个都没有 `open: true`，取 `ts` 最大的

---

## 二、探测脚本

```bash
python "scripts/find_vault.py"
python "scripts/find_vault.py" --json        # 机器可读输出
```

输出示例：

```
[OK] 找到 Obsidian 库：D:\MyVault
     来源：%APPDATA%\obsidian\obsidian.json (open=true)
     笔记将写入：D:\MyVault\微积分\
```

未找到时：

```
[FALLBACK] 未找到 Obsidian 库
     笔记将写入：微积分学习\笔记\
     提示：可以告诉我你的 Obsidian 库路径，我会记到 config.json 里
```

**容错要求**：

- `obsidian.json` 损坏或格式异常 → 视为"未找到"，不抛异常中断
- `path` 指向的目录**不存在** → 视为"未找到"
- Windows 路径中的反斜杠要正确处理（JSON 中为 `\\`）

---

## 三、手动指定 vault

学生给出路径后，写入 skill 目录下的 `config.json`：

```json
{
  "vault_path": "D:\\MyVault"
}
```

写入前**校验目录存在**；不存在则提示并不要写入。

对应的学生说法：
- "我的 Obsidian 库在 D:\MyVault"
- "obsidian 库路径是 …"
- 口令：`微积分 设置vault <路径>`

---

## 四、笔记落位规则

### 探测成功

```
<vault>/微积分/
├── 第01章-函数与极限/
│   ├── 等价无穷小替换.md
│   └── 洛必达法则的使用条件.md
├── 第03章-微分中值定理及导数的应用/
│   └── 弹性分析.md
└── _知识地图/
    └── 第01章-知识地图.md
```

### 探测失败（回退）

```
微积分学习/笔记/
├── 知识卡片/
│   └── 第01章-函数与极限/
└── 知识地图/
```

> 两种情形的**卡片内容与文件名完全一致**，日后搬迁不会破坏双链。

---

## 五、卡片格式规范

### 5.1 YAML frontmatter

```yaml
---
tags:
  - 微积分/第3章/导数应用
  - 微积分/经济应用
chapter: 第3章 微分中值定理及导数的应用
knowledge_point: 需求弹性
mastery: 能独立做          # 未接触 / 听过 / 能看懂 / 能独立做 / 能讲给别人
source: 苏德矿《微积分》第三版 上册 第3章
updated: 2026-09-17
aliases:
  - 弹性系数
  - 需求价格弹性
---
```

- `tags` 使用**层级标签** `微积分/第N章/<主题>`，Obsidian 中会自动形成树
- `aliases` 填常见别名，方便学生用不同叫法搜索
- `mastery` 与 `进度追踪.md` 中的评级保持一致

### 5.2 双向链接

- 正文用 `[[卡片名]]`，也可用 `[[卡片名|显示文字]]`
- 指向尚未建立的卡片 → 写 `待建卡片：xxx`，**不要**写成双链
- 卡片创建后，回头把 `待建卡片：xxx` 批量改成 `[[xxx]]`

### 5.3 MOC（内容地图）

同一章的卡片多了之后（≥ 8 张），生成一张 `第NN章-知识地图.md` 作为入口，
用双链把本章卡片全部串起来，形成 Layer 结构：

```
第01章-知识地图  →  等价无穷小替换 / 两个重要极限 / 间断点分类 / …
```

---

## 六、可选增强：obsidian-cli

若系统存在 `obsidian-cli`（`command -v obsidian-cli` 或 Windows 上 `where obsidian-cli` 有结果），可用它做增强：

| 能力 | 命令 |
|---|---|
| 设默认库 | `obsidian-cli set-default "<vault-folder-name>"` |
| 查默认库路径 | `obsidian-cli print-default --path-only` |
| 按标题搜索 | `obsidian-cli search "query"` |
| 全文搜索 | `obsidian-cli search-content "query"` |
| 新建笔记 | `obsidian-cli create "Folder/Note" --content "..." --open` |
| 移动/重命名（**会自动更新双链**） | `obsidian-cli move "old/path" "new/path"` |
| 删除 | `obsidian-cli delete "path/note"` |

**不存在 `obsidian-cli` 时全部改用纯文件读写**，功能不受影响——只是重命名笔记时需手动更新其他卡片里的双链（可用文本搜索替换完成）。

---

## 七、边界与禁忌

- ❌ 不要假设 vault 存在；每次写入前**重新探测**（学生可能换了库）
- ❌ 不要修改 `<vault>/.obsidian/` 下的任何配置（那是 Obsidian 自己的状态）
- ❌ 不要在隐藏目录（`.` 开头）下创建笔记，Obsidian 可能拒绝
- ❌ 不要删除学生已有的笔记；同名文件冲突时改为 `<名称>-微积分.md` 或先读后合并
- ✅ 写入前若同名文件已存在 → **先读取，再决定是追加还是合并**，并告知学生
