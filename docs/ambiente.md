# Ambiente local (Windows 10, PC do desenvolvedor)

Disco: C: ~6 GB livres (cheio), **D: ~48 GB livres** → tudo pesado vai para D:. RAM 24 GB, sem GPU NVIDIA detectada. JDK 21, Python 3.11 (pydantic, httpx, fastapi já instalados).

## Instalado / baixado
| Item | Caminho | Estado |
|---|---|---|
| Ollama **portátil** (zip, sem instalador) | `D:\Ollama\ollama.exe` | extraído, funcionando |
| Modelos Ollama | `D:\Ollama\models` | `qwen2.5:1.5b` |
| GGUF Qwen2.5-1.5B Q4_K_M (Apache 2.0) | `D:\dev\_downloads\models\` | baixado (redundante com o pull) |
| Instalador Ollama (1,8 GB) | `D:\dev\_downloads\OllamaSetup.exe` | não usado; pode apagar |
| Android cmdline-tools | `D:\AndroidSdk\cmdline-tools\latest` | extraído; pacotes do SDK pendentes |
| Android Studio | `D:\AndroidStudio` | já existia |

## Rodar o Ollama a partir de D: (sem instalar, sem tocar no C:)
```powershell
$env:OLLAMA_MODELS = "D:\Ollama\models"
Start-Process D:\Ollama\ollama.exe -ArgumentList serve -WindowStyle Hidden
D:\Ollama\ollama.exe pull qwen2.5:7b      # exemplo de outro modelo
```
Para tornar permanente: `[Environment]::SetEnvironmentVariable("OLLAMA_MODELS","D:\Ollama\models","User")`.

## Falta (precisa do usuário: aceite de licença do Google)
SDK do Android em D:
```powershell
D:\AndroidSdk\cmdline-tools\latest\bin\sdkmanager.bat --sdk_root=D:\AndroidSdk "platform-tools" "platforms;android-34" "build-tools;34.0.0"
```
Digite `y` nas licenças. Depois, no Android Studio: Settings → Android SDK → `D:\AndroidSdk`. No Moto G84: ativar Depuração USB.
