/**
 * nowp_hats.sp — игроки надевают шапки New-Old Weapons Pack.
 *
 * Шапки мода (21: по две на класс и берет на всех) в меню снаряжения не
 * видны — автор пометил их «Super-Secret». Плагин даёт меню !hat / !шапка,
 * запоминает выбор игрока на каждый класс и надевает шапку при каждом
 * появлении и после шкафа снабжения.
 *
 * Надевает VScript (scripts/vscripts/nowp_hats.nut): CTFPlayer::
 * GenerateAndWearItem есть у игроков с TF2 Classified 3.2.0. Список шапок —
 * configs/nowp_hats.cfg, его пишет tools/build.py из схемы мода.
 */
#pragma semicolon 1
#pragma newdecls required

#include <sourcemod>
#include <sdktools>
#include <clientprefs>

#define PLUGIN_VERSION "1.0.0"
#define MAX_HATS 64
#define GUARD "if(!(\"NOWP_Wear\" in getroottable()))IncludeScript(\"nowp_hats\",getroottable());"

public Plugin myinfo =
{
	name = "NOWP hats",
	author = "tgbot",
	description = "Шапки New-Old Weapons Pack для игроков",
	version = PLUGIN_VERSION,
	url = "https://gamebanana.com/mods/40389"
};

char g_sName[MAX_HATS][64];
int g_iId[MAX_HATS];
int g_iClassMask[MAX_HATS];      // бит N — класс N (TF2: 1 scout … 10 civilian)
int g_iHats = 0;

Cookie g_hCookie[11];
int g_iChoice[MAXPLAYERS + 1][11];   // номер шапки в списке + 1; 0 — без шапки

static const char g_sClassKey[11][] = {"", "scout", "sniper", "soldier",
	"demoman", "medic", "heavyweapons", "pyro", "spy", "engineer", "civilian"};

public void OnPluginStart()
{
	LoadHats();
	for (int c = 1; c <= 10; c++)
	{
		char name[32];
		Format(name, sizeof(name), "nowp_hat_%s", g_sClassKey[c]);
		g_hCookie[c] = new Cookie(name, "NOWP: шапка класса", CookieAccess_Private);
	}
	RegConsoleCmd("sm_hat", Cmd_Hat, "Выбрать шапку для текущего класса");
	RegConsoleCmd("sm_hats", Cmd_Hat, "Выбрать шапку для текущего класса");
	RegConsoleCmd("sm_шапка", Cmd_Hat, "Выбрать шапку для текущего класса");
	RegAdminCmd("nowp_hat_give", Cmd_Give, ADMFLAG_ROOT,
		"nowp_hat_give <userid> <номер в списке|0> — выбрать шапку за игрока");
	HookEvent("post_inventory_application", Ev_Inventory);
	for (int i = 1; i <= MaxClients; i++)
		if (IsClientInGame(i) && AreClientCookiesCached(i))
			OnClientCookiesCached(i);
}

void LoadHats()
{
	char path[PLATFORM_MAX_PATH];
	BuildPath(Path_SM, path, sizeof(path), "configs/nowp_hats.cfg");
	KeyValues kv = new KeyValues("nowp_hats");
	if (!kv.ImportFromFile(path) || !kv.GotoFirstSubKey())
	{
		LogError("нет %s — меню шапок будет пустым", path);
		delete kv;
		return;
	}
	g_iHats = 0;
	do
	{
		if (g_iHats >= MAX_HATS)
			break;
		kv.GetSectionName(g_sName[g_iHats], sizeof(g_sName[]));
		g_iId[g_iHats] = kv.GetNum("id");
		char classes[128];
		kv.GetString("classes", classes, sizeof(classes));
		g_iClassMask[g_iHats] = 0;
		for (int c = 1; c <= 10; c++)
			if (StrContains(classes, g_sClassKey[c]) != -1)
				g_iClassMask[g_iHats] |= (1 << c);
		g_iHats++;
	} while (kv.GotoNextKey());
	delete kv;
	PrintToServer("[NOWP] шапок в меню: %d", g_iHats);
}

public void OnClientCookiesCached(int client)
{
	for (int c = 1; c <= 10; c++)
	{
		char v[8];
		g_hCookie[c].Get(client, v, sizeof(v));
		g_iChoice[client][c] = StringToInt(v);
		if (g_iChoice[client][c] < 0 || g_iChoice[client][c] > g_iHats)
			g_iChoice[client][c] = 0;
	}
}

public void OnClientDisconnect(int client)
{
	for (int c = 1; c <= 10; c++)
		g_iChoice[client][c] = 0;
}

int PlayerClass(int client)
{
	if (!HasEntProp(client, Prop_Send, "m_iClass"))
		return 0;
	int c = GetEntProp(client, Prop_Send, "m_iClass");
	return (c >= 1 && c <= 10) ? c : 0;
}

// Имя шапки уходит в код VScript в кавычках: ни кавычек, ни «;» в нём
// быть не может — список пишет сборка, но проверяем и здесь.
bool SafeName(const char[] s)
{
	for (int i = 0; s[i] != '\0'; i++)
		if (s[i] == '"' || s[i] == ';' || s[i] == '\\')
			return false;
	return true;
}

void Run(int client, const char[] call)
{
	char code[512];
	Format(code, sizeof(code), "%s%s", GUARD, call);
	SetVariantString(code);
	AcceptEntityInput(client, "RunScriptCode", client, client);
}

void Wear(int client, int cls)
{
	int k = g_iChoice[client][cls] - 1;
	if (k < 0 || k >= g_iHats || !(g_iClassMask[k] & (1 << cls))
			|| !SafeName(g_sName[k]))
		return;
	char call[160];
	Format(call, sizeof(call), "NOWP_Wear(self,%d,\"%s\")", g_iId[k], g_sName[k]);
	Run(client, call);
}

void Unwear(int client, int k)
{
	if (k < 0 || k >= g_iHats)
		return;
	char call[64];
	Format(call, sizeof(call), "NOWP_Unwear(self,%d)", g_iId[k]);
	Run(client, call);
}

public void Ev_Inventory(Event event, const char[] name, bool dontBroadcast)
{
	int client = GetClientOfUserId(event.GetInt("userid"));
	if (client > 0)
		CreateTimer(0.2, Timer_Wear, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
}

public Action Timer_Wear(Handle timer, int userid)
{
	int client = GetClientOfUserId(userid);
	if (client > 0 && IsClientInGame(client) && IsPlayerAlive(client))
	{
		int cls = PlayerClass(client);
		if (cls)
			Wear(client, cls);
	}
	return Plugin_Stop;
}

void Choose(int client, int cls, int choice)
{
	int old = g_iChoice[client][cls] - 1;
	if (old >= 0 && old != choice - 1)
		Unwear(client, old);
	g_iChoice[client][cls] = choice;
	if (!IsFakeClient(client) && AreClientCookiesCached(client))
	{
		char v[8];
		IntToString(choice, v, sizeof(v));
		g_hCookie[cls].Set(client, v);
	}
	if (choice > 0 && IsPlayerAlive(client))
		Wear(client, cls);
}

public Action Cmd_Hat(int client, int args)
{
	if (client <= 0 || !IsClientInGame(client))
		return Plugin_Handled;
	int cls = PlayerClass(client);
	if (!cls)
	{
		ReplyToCommand(client, "[Шапки] Сначала выбери класс.");
		return Plugin_Handled;
	}
	Menu m = new Menu(Menu_Hat);
	m.SetTitle("Шапка для класса (New-Old Weapons Pack)");
	m.AddItem("0", "Без шапки");
	int n = 0;
	for (int k = 0; k < g_iHats; k++)
	{
		if (!(g_iClassMask[k] & (1 << cls)))
			continue;
		char key[8], label[80];
		IntToString(k + 1, key, sizeof(key));
		Format(label, sizeof(label), "%s%s", g_sName[k],
			g_iChoice[client][cls] == k + 1 ? "  ✓" : "");
		m.AddItem(key, label);
		n++;
	}
	if (n == 0)
	{
		delete m;
		ReplyToCommand(client, "[Шапки] Для этого класса шапок нет.");
		return Plugin_Handled;
	}
	m.Display(client, 30);
	return Plugin_Handled;
}

public int Menu_Hat(Menu menu, MenuAction action, int client, int item)
{
	if (action == MenuAction_Select)
	{
		char key[8];
		menu.GetItem(item, key, sizeof(key));
		int cls = PlayerClass(client);
		if (cls)
			Choose(client, cls, StringToInt(key));
	}
	else if (action == MenuAction_End)
		delete menu;
	return 0;
}

public Action Cmd_Give(int client, int args)
{
	char a[16], b[16];
	GetCmdArg(1, a, sizeof(a));
	GetCmdArg(2, b, sizeof(b));
	int target = GetClientOfUserId(StringToInt(a));
	int choice = StringToInt(b);
	if (target <= 0 || choice < 0 || choice > g_iHats)
	{
		ReplyToCommand(client, "nowp_hat_give <userid> <номер 1-%d | 0>", g_iHats);
		return Plugin_Handled;
	}
	int cls = PlayerClass(target);
	if (choice > 0 && !(g_iClassMask[choice - 1] & (1 << cls)))
	{
		ReplyToCommand(client, "[NOWP] «%s» не для этого класса", g_sName[choice - 1]);
		return Plugin_Handled;
	}
	Choose(target, cls, choice);
	ReplyToCommand(client, "[NOWP] %N: %s", target,
		choice ? g_sName[choice - 1] : "без шапки");
	return Plugin_Handled;
}
