; اسکریپت Inno Setup برای ساخت یک نصب‌کننده‌ی واقعی ویندوز (Setup.exe)
; پیش‌نیاز: ابتدا build_standalone_exe.bat را اجرا کرده و فایل
; dist\LPR-Camera-System.exe را ساخته باشید، سپس این فایل را با
; نرم‌افزار رایگان Inno Setup (www.jrsoftware.org/isinfo.php) کامپایل کنید.
; خروجی نهایی یک فایل "LPR-Setup.exe" است که کاربر با دوبار-کلیک،
; برنامه را مثل هر نرم‌افزار دیگری روی ویندوز نصب می‌کند
; (میانبر دسکتاپ + منوی استارت + امکان Uninstall از Control Panel).

[Setup]
AppName=سامانه ثبت خودکار پلاک
AppVersion=1.0
DefaultDirName={autopf}\LPRCameraSystem
DefaultGroupName=سامانه ثبت خودکار پلاک
OutputBaseFilename=LPR-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes

[Files]
Source: "dist\LPR-Camera-System.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "easyocr_models\*"; DestDir: "{app}\easyocr_models"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "yolo_model\*"; DestDir: "{app}\yolo_model"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\سامانه ثبت خودکار پلاک"; Filename: "{app}\LPR-Camera-System.exe"
Name: "{autodesktop}\سامانه ثبت خودکار پلاک"; Filename: "{app}\LPR-Camera-System.exe"

[Run]
Filename: "{app}\LPR-Camera-System.exe"; Description: "اجرای برنامه پس از نصب"; Flags: nowait postinstall skipifsilent
