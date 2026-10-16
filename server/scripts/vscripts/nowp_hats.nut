// nowp_hats.nut — надеть игроку шапку New-Old Weapons Pack по имени.
// Зовёт плагин nowp_hats через RunScriptCode на самом игроке (self).
// CTFPlayer::GenerateAndWearItem появился у игроков в TF2 Classified 3.2.0
// (до того — только у ботов); на старой версии игрок увидит сообщение.

::NOWP_HatsWorn <- function(player, item) {
    local out = []
    local e = null
    while ((e = Entities.FindByClassname(e, "tf_wearable")) != null)
        if ((e.GetOwner() == player || e.GetMoveParent() == player)
                && NetProps.GetPropInt(e,
                    "m_AttributeManager.m_Item.m_iItemDefinitionIndex") == item)
            out.append(e)
    return out
}

::NOWP_Wear <- function(player, item, name) {
    if (!("GenerateAndWearItem" in player)) {
        ClientPrint(player, 3, "[Шапки] Серверу нужна TF2 Classified 3.2.0 или новее.")
        return
    }
    if (NetProps.GetPropInt(player, "m_lifeState") != 0)
        return
    // Шкаф снабжения и возрождение зовут нас снова — вторую не надевать.
    if (NOWP_HatsWorn(player, item).len() > 0)
        return
    player.GenerateAndWearItem(name)
}

::NOWP_Unwear <- function(player, item) {
    foreach (e in NOWP_HatsWorn(player, item)) {
        if ("RemoveWearable" in player)
            player.RemoveWearable(e)
        else
            e.Kill()
    }
}
