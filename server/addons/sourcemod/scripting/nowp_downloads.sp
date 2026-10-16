/**
 * nowp_downloads.sp — отдаёт клиентам файлы New-Old Weapons Pack через FastDL.
 *
 * Сервер сам качает клиенту только карту. Модели, материалы и звуки
 * оружия клиент получит, лишь если они в таблице «downloadables», —
 * этот плагин кладёт туда каждый файл из configs/nowp_downloads.txt
 * (его пишет tools/build.py) на каждой карте.
 *
 * Сами файлы клиент берёт по sv_downloadurl (FastDL), а не с игрового
 * сервера: встроенная раздача Source — около 20 КБ/с.
 */
#pragma semicolon 1
#pragma newdecls required

#include <sourcemod>
#include <sdktools>

#define PLUGIN_VERSION "1.0.0"

public Plugin myinfo =
{
	name = "NOWP downloads",
	author = "tgbot",
	description = "New-Old Weapons Pack: файлы мода в таблицу загрузок",
	version = PLUGIN_VERSION,
	url = "https://gamebanana.com/mods/40389"
};

ConVar g_cvList;

public void OnPluginStart()
{
	g_cvList = CreateConVar("nowp_downloads_list",
		"configs/nowp_downloads.txt",
		"Список файлов для клиентов, путь от addons/sourcemod/.");
}

public void OnMapStart()
{
	char rel[PLATFORM_MAX_PATH], path[PLATFORM_MAX_PATH];
	g_cvList.GetString(rel, sizeof(rel));
	BuildPath(Path_SM, path, sizeof(path), "%s", rel);
	File f = OpenFile(path, "r");
	if (f == null)
	{
		LogError("нет списка %s — клиенты не скачают файлы мода", path);
		return;
	}
	char line[PLATFORM_MAX_PATH];
	int added = 0, missing = 0;
	while (f.ReadLine(line, sizeof(line)))
	{
		TrimString(line);
		if (line[0] == '\0' || (line[0] == '/' && line[1] == '/'))
			continue;
		// Файл должен быть и на сервере (в custom/…): иначе клиент
		// получит отказ и будет сыпать «Error Downloading».
		if (!FileExists(line, true))
		{
			missing++;
			continue;
		}
		AddFileToDownloadsTable(line);
		added++;
	}
	delete f;
	int total = GetStringTableNumStrings(FindStringTable("downloadables"));
	int cap = GetStringTableMaxStrings(FindStringTable("downloadables"));
	PrintToServer("[NOWP] в таблицу загрузок: %d файлов, нет на сервере: %d; "
		... "всего в таблице %d из %d", added, missing, total, cap);
	if (missing > 0)
		LogError("%d файлов из списка нет на сервере — выложи сборку целиком",
			missing);
}
