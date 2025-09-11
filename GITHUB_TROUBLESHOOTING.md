# GitHub MCP服务器故障排除指南

## 问题描述
当尝试使用GitHub MCP服务器创建仓库时，出现错误：
```
Error: Failed to create repository - None
```

## 根本原因
这个错误通常是由于以下原因之一造成的：

1. **缺少GitHub认证令牌** - 最常见的原因
2. **令牌权限不足** - 令牌没有足够的权限
3. **令牌格式错误** - 令牌格式不正确
4. **网络连接问题** - 无法连接到GitHub API

## 解决方案

### 1. 创建GitHub Personal Access Token

#### 步骤1：访问GitHub设置
1. 登录到您的GitHub账户
2. 点击右上角的头像，选择 "Settings"
3. 在左侧菜单中，点击 "Developer settings"
4. 选择 "Personal access tokens" > "Tokens (classic)"

#### 步骤2：生成新令牌
1. 点击 "Generate new token (classic)"
2. 填写令牌描述（例如："MCP Safety Tool"）
3. 设置过期时间（建议选择较长时间）
4. 选择以下权限：
   - ✅ `repo` (完整仓库访问权限)
   - ✅ `user` (用户信息访问权限)
   - ✅ `admin:org` (如果需要组织操作)
   - ✅ `delete_repo` (如果需要删除仓库)

#### 步骤3：复制令牌
1. 点击 "Generate token"
2. **立即复制令牌**（只显示一次）
3. 保存到安全的地方

### 2. 设置环境变量

#### 方法1：临时设置（当前会话）
```bash
export GITHUB_TOKEN="ghp_your_token_here"
```

#### 方法2：永久设置（推荐）
```bash
# 添加到 ~/.bashrc
echo 'export GITHUB_TOKEN="ghp_your_token_here"' >> ~/.bashrc
source ~/.bashrc

# 或添加到 ~/.zshrc（如果使用zsh）
echo 'export GITHUB_TOKEN="ghp_your_token_here"' >> ~/.zshrc
source ~/.zshrc
```

#### 方法3：项目级设置
```bash
# 在项目根目录创建 .env 文件
echo "GITHUB_TOKEN=ghp_your_token_here" > .env
```

### 3. 验证配置

运行测试脚本验证配置：
```bash
python test_github_connection.py
```

### 4. 常见问题解决

#### 问题1：令牌无效
```
Error: Failed to create repository - 401 Unauthorized
```
**解决方案：**
- 检查令牌是否正确复制
- 确认令牌没有过期
- 重新生成令牌

#### 问题2：权限不足
```
Error: Failed to create repository - 403 Forbidden
```
**解决方案：**
- 检查令牌权限设置
- 确保选择了 `repo` 权限
- 如果是组织仓库，确保有组织权限

#### 问题3：仓库已存在
```
Error: Failed to create repository - 422 Unprocessable Entity
```
**解决方案：**
- 选择不同的仓库名称
- 检查是否已存在同名仓库

#### 问题4：网络问题
```
Error: Failed to create repository - Connection timeout
```
**解决方案：**
- 检查网络连接
- 尝试使用VPN（如果在受限网络环境）
- 检查防火墙设置

### 5. 调试步骤

1. **检查环境变量**
   ```bash
   echo $GITHUB_TOKEN
   ```

2. **测试基本连接**
   ```python
   from github import Github
   client = Github("your_token")
   user = client.get_user()
   print(user.login)
   ```

3. **检查令牌权限**
   ```python
   from github import Github
   client = Github("your_token")
   user = client.get_user()
   print(f"公开仓库数: {user.public_repos}")
   ```

### 6. 安全注意事项

1. **永远不要将令牌提交到代码仓库**
2. **使用环境变量存储令牌**
3. **定期轮换令牌**
4. **只授予必要的权限**
5. **在不需要时撤销令牌**

### 7. 获取帮助

如果问题仍然存在：

1. 检查 [GitHub API文档](https://docs.github.com/en/rest)
2. 查看 [PyGithub文档](https://pygithub.readthedocs.io/)
3. 检查项目日志文件
4. 联系技术支持

## 测试命令

设置令牌后，运行以下命令测试：

```bash
# 设置令牌
export GITHUB_TOKEN="your_token_here"

# 运行测试脚本
python test_github_connection.py

# 或直接测试MCP服务器
python -m mcpuniverse.mcp.servers.github.server
```

