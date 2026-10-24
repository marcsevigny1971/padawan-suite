; Projet Padawan - installateur Inno Setup (par utilisateur, sans admin)
#define MyVer "2026.10.23"
[Setup]
AppId={{6F4C2A71-9B3E-4D8A-A5C1-50DA0A7A2310}
AppName=Projet Padawan
AppVersion={#MyVer}
AppVerName=Projet Padawan {#MyVer}
AppPublisher=Marc Sévigny
AppPublisherURL=https://marcsevigny.ca
AppSupportURL=https://github.com/marcsevigny1971/padawan-suite/issues
AppUpdatesURL=https://github.com/marcsevigny1971/padawan-suite/releases/latest
AppCopyright=© 2026 Marc Sévigny
VersionInfoVersion={#MyVer}.0
VersionInfoCompany=Marc Sévigny
VersionInfoDescription=Installation du Projet Padawan
VersionInfoProductName=Projet Padawan
VersionInfoProductVersion={#MyVer}
DefaultDirName={localappdata}\Padawan
DefaultGroupName=Padawan
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=out
OutputBaseFilename=Padawan-Setup
SetupIconFile=..\..\padawan_tray.ico
UninstallDisplayIcon={app}\padawan_tray.ico
UninstallDisplayName=Projet Padawan
Compression=zip/9
SolidCompression=no
WizardStyle=modern
WizardImageFile=wizard_100.bmp,wizard_200.bmp
WizardSmallImageFile=small_100.bmp,small_200.bmp
WizardImageStretch=no
DisableWelcomePage=no
DisableReadyPage=no
ShowLanguageDialog=no
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no
[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
[Messages]
fr.WelcomeLabel1=Bienvenue dans la Padawan Suite !
fr.WelcomeLabel2=Tu vas installer [name/ver] : une dizaine d'outils gratuits qui travaillent ensemble (IA locale, archives, notes, rangement automatique, boîte à outils, rétro…).%n%nAucun droit d'administrateur, aucun compte, aucun mot de passe. Compte quelques minutes : Python et les modules se téléchargent si besoin.%n%nSi Windows affiche « Windows a protégé votre ordinateur », c'est normal pour un petit logiciel gratuit : « Informations complémentaires » puis « Exécuter quand même ».%n%nClique Suivant pour commencer.
fr.FinishedHeadingLabel=C'est prêt, bienvenue !
fr.FinishedLabel=La Padawan Suite est installée. Son icône turquoise apparaîtra près de l'horloge : clic droit pour tous les outils.%n%nAstuce : Ctrl+Alt+R cherche dans toute la suite.%n%nNouvelles versions et suggestions : icône Padawan > « Ressources / GitHub ».
fr.StatusRunProgram=Préparation de la suite (Python, modules, raccourcis)… une fenêtre affiche la progression.
[Tasks]
Name: "ollama"; Description: "Installer aussi l'IA locale Ollama + le modèle d'IA (environ 6 Go à télécharger)"; Flags: unchecked
[Files]
Source: "stage\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config.json,arsenal.json,tasks.json,search_cache.json,archiveur_config.json"
Source: "stage\app\config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist
Source: "stage\installer_padawan.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "stage\LISEZMOI.txt"; DestDir: "{app}"; DestName: "LISEZMOI-INSTALLATION.txt"; Flags: ignoreversion
[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer_padawan.ps1"" -InstallDir ""{app}"" -Silent -NoCopy -Inno -NoLaunch {code:ExtraArgs}"; StatusMsg: "Configuration de Python, des modules et des raccourcis (quelques minutes)..."; Flags: waituntilterminated
Filename: "powershell.exe"; Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\_lancer.ps1"" -Script padawan39.py"; Description: "Lancer Padawan maintenant"; Flags: postinstall nowait runhidden skipifsilent
Filename: "powershell.exe"; Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\_lancer.ps1"" -Script premiers_pas.py -Arg --bienvenue"; Description: "Ouvrir le guide Premiers pas (5 minutes)"; Flags: postinstall nowait runhidden skipifsilent
Filename: "https://github.com/marcsevigny1971/padawan-suite"; Description: "Voir la page du projet sur GitHub (ressources et mises à jour)"; Flags: postinstall shellexec nowait skipifsilent unchecked
[Icons]
Name: "{userprograms}\Padawan\Padawan sur GitHub (ressources et mises à jour)"; Filename: "https://github.com/marcsevigny1971/padawan-suite"; IconFilename: "{app}\padawan_tray.ico"; Comment: "Page du projet, nouvelles versions et suggestions"
Name: "{userprograms}\Padawan\Réparer l'installation Padawan"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer_padawan.ps1"" -InstallDir ""{app}"" -Silent -NoCopy -NoLaunch"; WorkingDir: "{app}"; IconFilename: "{app}\padawan_tray.ico"; Comment: "Réinstalle les modules et les raccourcis sans toucher à tes données"
[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\desinstaller_padawan.ps1"" -Silent -KeepDir"; Flags: runhidden waituntilterminated; RunOnceId: "PadawanCleanup"
[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}"
[Code]
function ExtraArgs(Param: String): String;
begin
  Result := '';
  if WizardIsTaskSelected('ollama') then Result := Result + ' -Ollama';
  if ExpandConstant('{param:TEST|0}') = '1' then Result := Result + ' -Test';
  if WizardSilent then Result := Result + ' -NoLaunch';
end;
