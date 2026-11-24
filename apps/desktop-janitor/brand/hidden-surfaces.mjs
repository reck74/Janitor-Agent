// P18 (task F1-30, plan decision 2.10): the Janitor app does not offer Hermes'
// Skills Hub nor its plugin catalog, nor the one-click list of upstream's
// optional skills on the same tab (same reason: directive #19).
//
// Both are pages served by hermes-agent.nousresearch.com and embedded in an
// iframe, so the build cannot rebrand them (directive #17), and the Skills Hub
// installs skills from outside the Janitor catalog (directive #19). The iframes
// are never mounted, so the app makes no request to that host for them. Skills
// are chosen on the Skills page; a plugin can still be installed from a Git URL.

export const HIDDEN_SURFACE_PATCHES = [
  {
    id: 'P18-no-skills-hub',
    purpose: 'Capabilities → Skills: the embedded Hermes Skills Hub picker is never mounted',
    file: 'src/app/capabilities/index.tsx',
    find: '          {hubMounted && (\n            <EmbeddedHubPicker\n',
    replace: '          {false && hubMounted && (\n            <EmbeddedHubPicker\n',
    count: 1
  },
  {
    id: 'P18-no-official-skill-list',
    purpose: 'Capabilities → Skills: the «Disponibles para instalar» list (upstream optional skills, one-click install) stays empty',
    file: 'src/app/capabilities/skills/skills-tab.tsx',
    find: '    return filteredOfficial(catalog, query)\n  }, [installedSkillNames, officialData, query])\n',
    replace:
      '    return filteredOfficial(catalog, query).filter(() => false) // Janitor build: skills come from the Janitor catalog only\n' +
      '  }, [installedSkillNames, officialData, query])\n',
    count: 1
  },
  {
    id: 'P18-no-plugin-catalog-section',
    purpose: 'Capabilities → Plugins: the catalog section (title, browse button, sash) is hidden',
    file: 'src/app/capabilities/plugins/plugins-tab.tsx',
    find:
      '      <section\n        className="relative flex min-h-9 flex-col overflow-hidden border-t border-(--ui-stroke-secondary)"\n        ref={sectionRef}\n      >\n',
    replace: '      <section className="hidden" ref={sectionRef}>\n',
    count: 1
  },
  {
    id: 'P18-no-plugin-catalog-frame',
    purpose: 'Capabilities → Plugins: the embedded Hermes plugin catalog iframe is never mounted',
    file: 'src/app/capabilities/plugins/plugins-tab.tsx',
    find: '        {pickerMounted && (\n',
    replace: '        {false && pickerMounted && (\n',
    count: 1
  }
]
