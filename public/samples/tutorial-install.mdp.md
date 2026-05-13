# 安裝 foo CLI

依作業系統選擇安裝方式;三種選項都會把 `foo` 加入 PATH。

- **#prereq** `type:state` `status:active` `updated:2026-05-13`
  確認你有以下任一 package manager 可用:Homebrew (macOS)、apt (Debian/Ubuntu)、Scoop (Windows)。

- **#install-mac** `type:step` `variant-group:install` `variant:macOS`

  *Listing: macOS via Homebrew*

  ```bash
  brew install foo
  foo --version
  ```

  macOS 透過 Homebrew 安裝。若還沒裝 Homebrew,請先參考 https://brew.sh/。

- **#install-linux** `type:step` `variant-group:install` `variant:Linux`

  *Listing: Debian / Ubuntu via apt*

  ```bash
  sudo apt update
  sudo apt install foo
  foo --version
  ```

  Debian / Ubuntu 系列透過 apt 安裝。其他發行版請查 https://foo.dev/install。

- **#install-windows** `type:step` `variant-group:install` `variant:Windows`

  *Listing: Windows via Scoop*

  ```powershell
  scoop install foo
  foo --version
  ```

  Windows 透過 Scoop 安裝。若沒有 Scoop,改用 Chocolatey:`choco install foo`。

- **#verify** `type:step` `status:active`

  *Listing: 驗證安裝*

  ```bash
  foo --version
  foo init my-project
  cd my-project
  foo run
  ```

  跑完 `foo run` 應該看到 `Hello from foo!`。若看到 `command not found`,
  確認 `foo` 已加入 PATH(可能要重開 terminal)。

- **#troubleshoot** `type:reference`

  常見問題:
  - **permission denied**:Linux/macOS 可能需 `sudo`,或改裝到 user 目錄。
  - **command not found**:重開 terminal;或檢查 `echo $PATH` 是否包含 foo 的安裝位置。
  - **網路錯誤**:確認可連到 https://registry.foo.dev/。
