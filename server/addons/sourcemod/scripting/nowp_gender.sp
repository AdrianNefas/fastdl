/**
 * nowp_gender.sp — второй пол персонажа на выбор игрока.
 *
 * Моды женских моделей заменяют модель класса по тому же пути, и через
 * FastDL такая подмена у клиента не работает: скачанное игра ищет
 * последним. Поэтому модель лежит под своим путём (configs/nowp_models.cfg)
 * и надевается конкретному игроку через VScript
 * SetCustomModelWithClassAnimations — анимации класса остаются.
 *
 * Только RED и BLU: у моделей из обычного TF2 нет раскрасок зелёной и
 * жёлтой команд Classified.
 *
 * !gender / !пол — меню; nowp_gender_set <userid> <0|1> — за игрока или
 * бота (так ставит пол ботам режиссёр).
 */
#pragma semicolon 1
#pragma newdecls required

#include <sourcemod>
#include <sdktools>
#include <clientprefs>

#define PLUGIN_VERSION "1.0.1"

public Plugin myinfo =
{
	name = "NOWP gender",
	author = "tgbot",
	description = "Второй пол персонажа на выбор игрока",
	version = PLUGIN_VERSION,
	url = ""
};

static const char g_sClassKey[11][] = {"", "scout", "sniper", "soldier",
	"demoman", "medic", "heavyweapons", "pyro", "spy", "engineer", "civilian"};

char g_sModel[11][PLATFORM_MAX_PATH];   // женская модель класса; "" — нет
Cookie g_hCookie;
int g_iChoice[MAXPLAYERS + 1][11];      // 1 — женская
// Ставили ли модель мы. В 1.0.0 сброс SetCustomModel("") шёл каждому
// игроку на каждом возрождении — и снимал модели других плагинов
// (prop hunt, VSH и т. п.), которые к полу отношения не имеют.
bool g_bOurs[MAXPLAYERS + 1];

public void OnPluginStart()
{
	g_hCookie = new Cookie("nowp_gender", "NOWP: пол по классам", CookieAccess_Private);
	RegConsoleCmd("sm_gender", Cmd_Gender, "Пол персонажа для текущего класса");
	RegConsoleCmd("sm_пол", Cmd_Gender, "Пол персонажа для текущего класса");
	RegAdminCmd("nowp_gender_set", Cmd_Set, ADMFLAG_ROOT,
		"nowp_gender_set <userid> <0|1> — пол за игрока или бота (текущий класс)");
	HookEvent("post_inventory_application", Ev_Inventory);
	HookEvent("player_team", Ev_Team);
	LoadModels();
	// Перезагрузка плагина посреди карты: выбор игроков — из кук сразу,
	// а не после перезахода.
	for (int i = 1; i <= MaxClients; i++)
		if (IsClientInGame(i) && AreClientCookiesCached(i))
			OnClientCookiesCached(i);
}

void LoadModels()
{
	char path[PLATFORM_MAX_PATH];
	BuildPath(Path_SM, path, sizeof(path), "configs/nowp_models.cfg");
	KeyValues kv = new KeyValues("nowp_models");
	int n = 0;
	if (kv.ImportFromFile(path))
	{
		for (int c = 1; c <= 10; c++)
		{
			g_sModel[c][0] = '\0';
			if (kv.JumpToKey(g_sClassKey[c]))
			{
				kv.GetString("female", g_sModel[c], sizeof(g_sModel[]));
				kv.GoBack();
				if (g_sModel[c][0])
					n++;
			}
		}
	}
	else
		LogError("нет %s — женских моделей нет", path);
	delete kv;
	PrintToServer("[NOWP] женских моделей классов: %d", n);
}

public void OnMapStart()
{
	for (int c = 1; c <= 10; c++)
		if (g_sModel[c][0])
			PrecacheModel(g_sModel[c], true);
}

public void OnClientCookiesCached(int client)
{
	char v[16];
	g_hCookie.Get(client, v, sizeof(v));
	for (int c = 1; c <= 10; c++)
		g_iChoice[client][c] = (strlen(v) >= c && v[c - 1] == '1') ? 1 : 0;
}

public void OnClientDisconnect(int client)
{
	for (int c = 1; c <= 10; c++)
		g_iChoice[client][c] = 0;
	g_bOurs[client] = false;
}

int PlayerClass(int client)
{
	if (!HasEntProp(client, Prop_Send, "m_iClass"))
		return 0;
	int c = GetEntProp(client, Prop_Send, "m_iClass");
	return (c >= 1 && c <= 10) ? c : 0;
}

void SaveCookie(int client)
{
	if (IsFakeClient(client) || !AreClientCookiesCached(client))
		return;
	char v[16];
	for (int c = 1; c <= 10; c++)
		v[c - 1] = g_iChoice[client][c] ? '1' : '0';
	v[10] = '\0';
	g_hCookie.Set(client, v);
}

void Apply(int client)
{
	if (!IsClientInGame(client) || !IsPlayerAlive(client))
		return;
	int cls = PlayerClass(client);
	int team = GetClientTeam(client);
	char code[PLATFORM_MAX_PATH + 96];
	if (cls && g_sModel[cls][0] && g_iChoice[client][cls] && (team == 2 || team == 3))
	{
		Format(code, sizeof(code),
			"self.SetCustomModelWithClassAnimations(\"%s\")", g_sModel[cls]);
		g_bOurs[client] = true;
	}
	else if (g_bOurs[client])
	{
		strcopy(code, sizeof(code), "self.SetCustomModel(\"\")");
		g_bOurs[client] = false;
	}
	else
		return;
	SetVariantString(code);
	AcceptEntityInput(client, "RunScriptCode", client, client);
}

public void Ev_Inventory(Event event, const char[] name, bool dontBroadcast)
{
	int client = GetClientOfUserId(event.GetInt("userid"));
	if (client > 0)
		CreateTimer(0.1, Timer_Apply, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
}

public void Ev_Team(Event event, const char[] name, bool dontBroadcast)
{
	int client = GetClientOfUserId(event.GetInt("userid"));
	if (client > 0)
		CreateTimer(0.2, Timer_Apply, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
}

public Action Timer_Apply(Handle timer, int userid)
{
	int client = GetClientOfUserId(userid);
	if (client > 0)
		Apply(client);
	return Plugin_Stop;
}

public Action Cmd_Gender(int client, int args)
{
	if (client <= 0 || !IsClientInGame(client))
		return Plugin_Handled;
	int cls = PlayerClass(client);
	if (!cls || !g_sModel[cls][0])
	{
		ReplyToCommand(client, "[Пол] Для этого класса второй модели пока нет.");
		return Plugin_Handled;
	}
	Menu m = new Menu(Menu_Gender);
	m.SetTitle("Пол персонажа (этот класс)");
	m.AddItem("0", g_iChoice[client][cls] ? "Мужской" : "Мужской  ✓");
	m.AddItem("1", g_iChoice[client][cls] ? "Женский  ✓" : "Женский");
	m.Display(client, 30);
	return Plugin_Handled;
}

public int Menu_Gender(Menu menu, MenuAction action, int client, int item)
{
	if (action == MenuAction_Select)
	{
		char key[4];
		menu.GetItem(item, key, sizeof(key));
		int cls = PlayerClass(client);
		if (cls)
		{
			g_iChoice[client][cls] = StringToInt(key);
			SaveCookie(client);
			Apply(client);
			int team = GetClientTeam(client);
			if (g_iChoice[client][cls] && team != 2 && team != 3)
				PrintToChat(client, "[Пол] Работает за RED и BLU.");
		}
	}
	else if (action == MenuAction_End)
		delete menu;
	return 0;
}

public Action Cmd_Set(int client, int args)
{
	char a[16], b[8];
	GetCmdArg(1, a, sizeof(a));
	GetCmdArg(2, b, sizeof(b));
	int target = GetClientOfUserId(StringToInt(a));
	if (target <= 0)
	{
		ReplyToCommand(client, "nowp_gender_set <userid> <0|1>");
		return Plugin_Handled;
	}
	int cls = PlayerClass(target);
	if (!cls || !g_sModel[cls][0])
	{
		ReplyToCommand(client, "[NOWP] для класса %d второй модели нет", cls);
		return Plugin_Handled;
	}
	g_iChoice[target][cls] = StringToInt(b) ? 1 : 0;
	SaveCookie(target);
	Apply(target);
	ReplyToCommand(client, "[NOWP] %N: %s", target,
		g_iChoice[target][cls] ? "женский" : "мужской");
	return Plugin_Handled;
}
