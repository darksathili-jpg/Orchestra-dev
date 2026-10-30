const $ = id => document.getElementById(id);
const element = (tag, text, className) => { const node = document.createElement(tag); node.textContent = text; if (className) node.className = className; return node; };
async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Erreur serveur');
  return data;
}
function options(select, records, label) {
  select.replaceChildren();
  for (const record of records) {
    const option = document.createElement('option');
    option.value = record.id;
    option.textContent = label(record);
    select.append(option);
  }
}
function addItem(container, title, detail) {
  const row = element('div', '', 'item');
  row.append(element('strong', title), element('small', detail));
  container.append(row);
}
async function refresh() {
  const data = await request('/api/snapshot');
  $('projectCount').textContent = data.projects.length;
  $('missionCount').textContent = data.missions.length;
  $('criterionCount').textContent = data.criteria.filter(c => c.status === 'NON_VÉRIFIÉ').length;
  options($('projectSelect'), data.projects, p => p.name);
  options($('criterionMission'), data.missions, m => m.title);
  for (const key of ['projects', 'missions', 'criteria']) $(key + 'List').replaceChildren();
  for (const p of data.projects) addItem($('projectsList'), p.name, p.repo || 'Dépôt non renseigné');
  for (const m of data.missions) addItem($('missionsList'), m.title, m.state);
  for (const c of data.criteria) addItem($('criteriaList'), c.description, c.status);
}
function bind(formId, path) {
  $(formId).addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      await request(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      $('notice').textContent = 'Enregistrement effectué.';
      form.reset();
      await refresh();
    } catch(error) { $('notice').textContent = 'Erreur : ' + error.message; }
  });
}
bind('projectForm', '/api/projects');
bind('missionForm', '/api/missions');
bind('criterionForm', '/api/criteria');
refresh().catch(error => { $('notice').textContent = 'Impossible de charger les données : ' + error.message; });
