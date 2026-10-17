/**
 * nowp_hats.sp — игроки надевают шапки New-Old Weapons Pack и оригинальной TF2.
 *
 * Шапки мода (21: по две на класс и берет на всех) в меню снаряжения не
 * видны — автор пометил их «Super-Secret». С 1.1.0 к ним добавлены шапки
 * TF2 (~900): Classified монтирует VPK TF2, модели у игрока есть, а
 * записи предметов — scripts/items/custom_weapons_additions.txt
 * (tools/tf2hats.py). Плагин даёт меню !hat / !шапка, запоминает выбор
 * игрока на каждый класс и надевает шапку при каждом появлении и после
 * шкафа снабжения.
 *
 * Надевает VScript (scripts/vscripts/nowp_hats.nut): CTFPlayer::
 * GenerateAndWearItem есть у игроков с TF2 Classified 3.2.0. Списки —
 * configs/nowp_hats.cfg (пишет tools/build.py) и configs/tf2_hats.cfg
 * (пишет tools/tf2hats.py); второго может не быть — тогда только мод.
 */
#pragma semicolon 1
#pragma newdecls required

#include <sourcemod>
#include <sdktools>
#include <clientprefs>

#define PLUGIN_VERSION "1.1.0"
// До 1.1.0 было 64: шапок было 21. Шапок TF2 сейчас 886 — с запасом на
// новые выпуски TF2 без пересборки плагина.
#define MAX_HATS 1536
#define SRC_NOWP 0
#define SRC_TF2 1
#define GUARD "if(!(\"NOWP_Wear\" in getroottable()))IncludeScript(\"nowp_hats\",getroottable());"

public Plugin myinfo =
{
	name = "NOWP hats",
	author = "tgbot",
	description = "Шапки New-Old Weapons Pack и TF2 для игроков",
	version = PLUGIN_VERSION,
	url = "https://github.com/AdrianNefas/fastdl"
};

char g_sName[MAX_HATS][64];
int g_iId[MAX_HATS];
int g_iClassMask[MAX_HATS];      // бит N — класс N (TF2: 1 scout … 10 civilian)
int g_iSrc[MAX_HATS];
int g_iHats = 0;
int g_iNowp = 0;                 // сколько из них — шапки мода (идут первыми)

// До 1.1.0 кука хранила номер шапки в списке + 1. Со вторым списком
// номер в списке уже не постоянен (TF2 добавит шапок — всё съедет),
// поэтому теперь храним номер предмета, под новым именем куки.
Cookie g_hCookie[11];
Cookie g_hOldCookie[11];
int g_iChoice[MAXPLAYERS + 1][11];   // номер предмета; 0 — без шапки

static const char g_sClassKey[11][] = {"", "scout", "sniper", "soldier",
	"demoman", "medic", "heavyweapons", "pyro", "spy", "engineer", "civilian"};

public void OnPluginStart()
{
	g_iHats = 0;
	LoadHats("nowp_hats.cfg", SRC_NOWP);
	g_iNowp = g_iHats;
	LoadHats("tf2_hats.cfg", SRC_TF2);
	PrintToServer("[NOWP] шапок в меню: %d (мод %d, TF2 %d)", g_iHats,
		g_iNowp, g_iHats - g_iNowp);
	for (int c = 1; c <= 10; c++)
	{
		char name[32];
		Format(name, sizeof(name), "nowp_hatid_%s", g_sClassKey[c]);
		g_hCookie[c] = new Cookie(name, "NOWP: шапка класса (номер предмета)",
			CookieAccess_Private);
		Format(name, sizeof(name), "nowp_hat_%s", g_sClassKey[c]);
		g_hOldCookie[c] = new Cookie(name, "NOWP: шапка класса (до 1.1.0)",
			CookieAccess_Private);
	}
	RegConsoleCmd("sm_hat", Cmd_Hat, "!hat [слово] — шапка для текущего класса");
	RegConsoleCmd("sm_hats", Cmd_Hat, "!hats [слово] — шапка для текущего класса");
	RegConsoleCmd("sm_шапка", Cmd_Hat, "!шапка [слово] — шапка для текущего класса");
	RegAdminCmd("nowp_hat_give", Cmd_Give, ADMFLAG_ROOT,
		"nowp_hat_give <userid> <номер предмета|0> — выбрать шапку за игрока");
	HookEvent("post_inventory_application", Ev_Inventory);
	for (int i = 1; i <= MaxClients; i++)
		if (IsClientInGame(i) && AreClientCookiesCached(i))
			OnClientCookiesCached(i);
}

void LoadHats(const char[] file, int src)
{
	char path[PLATFORM_MAX_PATH];
	BuildPath(Path_SM, path, sizeof(path), "configs/%s", file);
	if (!FileExists(path))
	{
		// tf2_hats.cfg необязателен: без схемы шапок TF2 на сервере
		// этих предметов нет, и меню их показывать не должно.
		if (src == SRC_NOWP)
			LogError("нет %s — шапок мода в меню не будет", path);
		return;
	}
	KeyValues kv = new KeyValues("hats");
	if (!kv.ImportFromFile(path) || !kv.GotoFirstSubKey())
	{
		LogError("%s не читается — его шапок в меню не будет", path);
		delete kv;
		return;
	}
	do
	{
		if (g_iHats >= MAX_HATS)
		{
			LogError("в %s больше шапок, чем MAX_HATS=%d: остальные не в меню",
				path, MAX_HATS);
			break;
		}
		kv.GetSectionName(g_sName[g_iHats], sizeof(g_sName[]));
		g_iId[g_iHats] = kv.GetNum("id");
		if (g_iId[g_iHats] <= 0 || Find(g_iId[g_iHats]) != -1
				|| !SafeName(g_sName[g_iHats]))
			continue;
		char classes[128];
		kv.GetString("classes", classes, sizeof(classes));
		g_iClassMask[g_iHats] = 0;
		for (int c = 1; c <= 10; c++)
			if (StrContains(classes, g_sClassKey[c]) != -1)
				g_iClassMask[g_iHats] |= (1 << c);
		g_iSrc[g_iHats] = src;
		g_iHats++;
	} while (kv.GotoNextKey());
	delete kv;
}

// Номер в списке по номеру предмета; -1 — нет такого.
int Find(int id)
{
	for (int k = 0; k < g_iHats; k++)
		if (g_iId[k] == id)
			return k;
	return -1;
}

public void OnClientCookiesCached(int client)
{
	for (int c = 1; c <= 10; c++)
	{
		char v[12];
		g_hCookie[c].Get(client, v, sizeof(v));
		int id = StringToInt(v);
		if (v[0] == '\0')
		{
			// Выбор, сделанный до 1.1.0: номер в nowp_hats.cfg + 1. Порядок
			// шапок мода в файле тот же, что был, поэтому переводится.
			g_hOldCookie[c].Get(client, v, sizeof(v));
			int old = StringToInt(v);
			if (old >= 1 && old <= g_iNowp)
			{
				id = g_iId[old - 1];
				IntToString(id, v, sizeof(v));
				g_hCookie[c].Set(client, v);
			}
		}
		g_iChoice[client][c] = Find(id) != -1 ? id : 0;
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

bool Fits(int k, int cls)
{
	return k >= 0 && k < g_iHats && (g_iClassMask[k] & (1 << cls)) != 0;
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
	int k = Find(g_iChoice[client][cls]);
	if (!Fits(k, cls))
		return;
	char call[160];
	Format(call, sizeof(call), "NOWP_Wear(self,%d,\"%s\")", g_iId[k], g_sName[k]);
	Run(client, call);
}

void Unwear(int client, int id)
{
	if (id <= 0)
		return;
	char call[64];
	Format(call, sizeof(call), "NOWP_Unwear(self,%d)", id);
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

void Choose(int client, int cls, int id)
{
	int old = g_iChoice[client][cls];
	if (old != id)
		Unwear(client, old);
	g_iChoice[client][cls] = id;
	if (!IsFakeClient(client) && AreClientCookiesCached(client))
	{
		char v[12];
		IntToString(id, v, sizeof(v));
		g_hCookie[cls].Set(client, v);
	}
	if (id > 0 && IsPlayerAlive(client))
		Wear(client, cls);
}

int Count(int cls, int src, const char[] find)
{
	int n = 0;
	for (int k = 0; k < g_iHats; k++)
		if (Fits(k, cls) && (src < 0 || g_iSrc[k] == src)
				&& (find[0] == '\0' || StrContains(g_sName[k], find, false) != -1))
			n++;
	return n;
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
	if (args > 0)
	{
		// !hat <слово>: ~300 шапок на класс листать по 7 на странице
		// незачем — сразу список найденного.
		char find[32];
		GetCmdArgString(find, sizeof(find));
		StripQuotes(find);
		TrimString(find);
		if (Count(cls, -1, find) == 0)
		{
			ReplyToCommand(client, "[Шапки] «%s» — для этого класса ничего нет.", find);
			return Plugin_Handled;
		}
		ShowList(client, cls, -1, find);
		return Plugin_Handled;
	}
	int nNowp = Count(cls, SRC_NOWP, ""), nTf2 = Count(cls, SRC_TF2, "");
	if (nNowp + nTf2 == 0)
	{
		ReplyToCommand(client, "[Шапки] Для этого класса шапок нет.");
		return Plugin_Handled;
	}
	Menu m = new Menu(Menu_Top);
	int k = Find(g_iChoice[client][cls]);
	m.SetTitle("Шапка для класса\nСейчас: %s\nПоиск: !hat слово",
		Fits(k, cls) ? g_sName[k] : "без шапки");
	m.AddItem("off", "Без шапки");
	char label[64];
	Format(label, sizeof(label), "Шапки мода (%d)", nNowp);
	m.AddItem("nowp", label, nNowp ? ITEMDRAW_DEFAULT : ITEMDRAW_DISABLED);
	Format(label, sizeof(label), "Шапки TF2 (%d)", nTf2);
	m.AddItem("tf2", label, nTf2 ? ITEMDRAW_DEFAULT : ITEMDRAW_DISABLED);
	m.Display(client, 30);
	return Plugin_Handled;
}

void ShowList(int client, int cls, int src, const char[] find)
{
	Menu m = new Menu(Menu_Hat);
	if (find[0] != '\0')
		m.SetTitle("Шапки: «%s»", find);
	else
		m.SetTitle(src == SRC_TF2 ? "Шапки TF2" : "Шапки мода");
	for (int k = 0; k < g_iHats; k++)
	{
		if (!Fits(k, cls) || (src >= 0 && g_iSrc[k] != src)
				|| (find[0] != '\0' && StrContains(g_sName[k], find, false) == -1))
			continue;
		char key[12], label[80];
		IntToString(g_iId[k], key, sizeof(key));
		Format(label, sizeof(label), "%s%s", g_sName[k],
			g_iChoice[client][cls] == g_iId[k] ? "  ✓" : "");
		m.AddItem(key, label);
	}
	m.ExitBackButton = true;
	// 60 с, а не 30: в списке TF2 до 40 страниц.
	m.Display(client, 60);
}

public int Menu_Top(Menu menu, MenuAction action, int client, int item)
{
	if (action == MenuAction_Select)
	{
		char key[8];
		menu.GetItem(item, key, sizeof(key));
		int cls = PlayerClass(client);
		if (!cls)
			return 0;
		if (StrEqual(key, "off"))
			Choose(client, cls, 0);
		else
			ShowList(client, cls, StrEqual(key, "tf2") ? SRC_TF2 : SRC_NOWP, "");
	}
	else if (action == MenuAction_End)
		delete menu;
	return 0;
}

public int Menu_Hat(Menu menu, MenuAction action, int client, int item)
{
	if (action == MenuAction_Select)
	{
		char key[12];
		menu.GetItem(item, key, sizeof(key));
		// Меню висит до минуты: за это время игрок мог сменить класс, и
		// шапка чужого класса записалась бы в куку нового (1.0.1).
		int cls = PlayerClass(client);
		int id = StringToInt(key);
		if (cls && Fits(Find(id), cls))
			Choose(client, cls, id);
		else if (cls)
			PrintToChat(client, "[Шапки] Класс сменился — открой !hat ещё раз.");
	}
	else if (action == MenuAction_Cancel && item == MenuCancel_ExitBack)
	{
		if (IsClientInGame(client))
			Cmd_Hat(client, 0);
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
	int id = StringToInt(b);
	int k = Find(id);
	// До 1.1.0 второй аргумент был номером в списке; теперь — номер
	// предмета (как в схеме и в dir_wear режиссёра).
	if (target <= 0 || id < 0 || (id > 0 && k == -1))
	{
		ReplyToCommand(client, "nowp_hat_give <userid> <номер предмета | 0>");
		return Plugin_Handled;
	}
	int cls = PlayerClass(target);
	// Наблюдатель без класса: куки класса 0 нет (g_hCookie[0] — null),
	// и Choose падал на ней ошибкой плагина (1.0.1).
	if (!cls)
	{
		ReplyToCommand(client, "[NOWP] у игрока нет класса");
		return Plugin_Handled;
	}
	if (id > 0 && !Fits(k, cls))
	{
		ReplyToCommand(client, "[NOWP] «%s» не для этого класса", g_sName[k]);
		return Plugin_Handled;
	}
	Choose(target, cls, id);
	ReplyToCommand(client, "[NOWP] %N: %s", target, id ? g_sName[k] : "без шапки");
	return Plugin_Handled;
}
