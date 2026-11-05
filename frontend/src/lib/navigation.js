/**
 * Keep only the navigation items a user may open (permission + tenant module
 * flag) and drop groups left empty. Pure so it can be unit tested without React.
 */
export function visibleNavGroups(groups, hasPerm, enabledModules = {}) {
  return groups
    .map((g) => ({
      ...g,
      items: g.items.filter((n) =>
        !(n.module && enabledModules[n.module] === false) && hasPerm(n.perm)),
    }))
    .filter((g) => g.items.length > 0);
}
