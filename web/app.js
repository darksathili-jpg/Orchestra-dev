const $ = id => document.getElementById(id);
const element = (tag, text, className) => { const node = document.createElement(tag); node.textContent = text; if (className) node.className = className; return node; };
let snapshot = { missions: [] };
let review = null;
let reviewRequest = 0;
async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Erreur serveur');
  return data;
}
const post = (path, data) => request(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Orchestra-Request': '1' }, body: JSON.stringify(data) });
function options(select, records, label) {
  const selected = select.value;
  select.replaceChildren();
  for (const record of records) {
    const option = element('option', label(record));
    option.value = record.id;
    select.append(option);
  }
  if (records.some(record => record.id === selected)) select.value = selected;
}
function addItem(container, title, detail) {
  const row = element('div', '', 'item');
  row.append(element('strong', title), element('small', detail));
  container.append(row);
}
const dateLabel = value => value ? new Date(value).toLocaleString('fr-FR') : 'Non vérifié';
async function refresh(selection = {}) {
  snapshot = await request('/api/snapshot');
  $('projectCount').textContent = snapshot.projects.length;
  $('missionCount').textContent = snapshot.missions.length;
  $('criterionCount').textContent = snapshot.criteria.filter(c => c.status === 'NON_VÉRIFIÉ').length;
  options($('projectSelect'), snapshot.projects, p => p.name);
  for (const id of ['criterionMission', 'briefMission', 'reviewMission']) options($(id), snapshot.missions, m => m.title);
  for (const [id, value] of Object.entries(selection)) $(id).value = value;
  for (const key of ['projects', 'missions', 'criteria']) $(key + 'List').replaceChildren();
  for (const p of snapshot.projects) addItem($('projectsList'), p.name, p.repo || 'Dépôt non renseigné');
  for (const m of snapshot.missions) addItem($('missionsList'), m.title, m.state);
  for (const c of snapshot.criteria) addItem($('criteriaList'), c.description, c.status);
  await loadReview();
}
function labeled(text, control) {
  const label = element('label', text);
  label.append(control);
  return label;
}
function renderReview(data) {
  $('reviewState').textContent = data.mission.title + ' · ' + data.mission.state + ' · Version des critères : ' + data.mission.criteria_revision;
  $('blockers').replaceChildren(...(data.blockers.length ? data.blockers : ['Tous les critères sont conformes avec preuve et date.']).map(text => element('li', text)));
  $('approvalBlocker').textContent = data.approval_blocker;
  const frozen = ['VALIDÉE', 'PUBLIÉE', 'PUBLICATION_ÉCHOUÉE'].includes(data.mission.state);
  $('verificationList').replaceChildren();
  for (const criterion of data.criteria) {
    const card = element('article', '', 'item criterion');
    card.dataset.criterionId = criterion.id;
    card.append(element('h3', criterion.description), element('p', criterion.status, 'status status-' + criterion.status.toLowerCase()));
    card.append(element('p', 'Vérifié le : ' + dateLabel(criterion.verified_at)));
    card.append(element('p', criterion.evidence || 'Aucune preuve enregistrée.', 'proof'));
    const form = document.createElement('form');
    const status = document.createElement('select');
    status.name = 'status';
    options(status, ['CONFORME', 'NON_CONFORME'].map(id => ({ id })), row => row.id);
    if (criterion.status !== 'NON_VÉRIFIÉ') status.value = criterion.status;
    const evidence = document.createElement('textarea');
    evidence.name = 'evidence'; evidence.required = true; evidence.maxLength = 8000; evidence.rows = 3;
    evidence.value = criterion.evidence || '';
    const submit = element('button', 'Enregistrer la vérification'); submit.type = 'submit';
    for (const control of [status, evidence, submit]) control.disabled = frozen;
    form.append(labeled('Résultat pour « ' + criterion.description + ' »', status), labeled('Preuve pour « ' + criterion.description + ' »', evidence), submit);
    form.addEventListener('submit', async event => {
      event.preventDefault(); submit.disabled = true;
      try {
        await post('/api/verifications', { criterion_id: criterion.id, status: status.value, evidence: evidence.value, expected_revision: data.mission.criteria_revision });
        $('notice').textContent = 'Vérification enregistrée. Toute demande d’approbation précédente est invalidée.';
        await refresh();
      } catch (error) {
        $('notice').textContent = error.message + ' Votre saisie est conservée ; actualisez pour examiner la version courante.';
        submit.disabled = frozen;
      }
    });
    if (frozen) card.append(element('p', 'Critères gelés après approbation historique.'));
    card.append(form); $('verificationList').append(card);
  }
  options($('nextState'), data.allowed_transitions.map(id => ({ id })), row => row.id);
  $('transitionButton').disabled = !data.allowed_transitions.length;
  $('nextState').disabled = !data.allowed_transitions.length;
  $('verificationHistory').replaceChildren();
  for (const entry of data.verification_history) {
    const criterion = data.criteria.find(c => c.id === entry.criterion_id);
    addItem($('verificationHistory'), (criterion?.description || entry.criterion_id) + ' · ' + entry.status,
      dateLabel(entry.verified_at) + ' · ' + entry.evidence + (entry.source === 'legacy-untrusted' ? ' · Historique V0.3.1 non authentifié' : ' · Résultat déclaré'));
  }
  if (!data.verification_history.length) addItem($('verificationHistory'), 'Aucune vérification journalisée.', 'Les anciennes preuves sans événement restent visibles sur les critères.');
  $('decisionHistory').replaceChildren();
  for (const decision of data.decisions) addItem($('decisionHistory'), 'REFUS · ' + decision.target,
    dateLabel(decision.timestamp) + ' · version ' + decision.criteria_revision + ' · ' + decision.reason + ' · Aucune identité authentifiée');
  for (const event of data.events.filter(e => ['VALIDÉE', 'PUBLIÉE'].includes(e.next_state) && e.previous_state !== e.next_state)) {
    addItem($('decisionHistory'), 'Décision historique · ' + event.next_state, event.reason + ' · Identité non authentifiée dans la version historique');
  }
  if (!$('decisionHistory').children.length) addItem($('decisionHistory'), 'Aucune décision enregistrée.', 'Approbation humaine indisponible.');
  $('workflowHistory').replaceChildren();
  for (const event of data.events) addItem($('workflowHistory'), (event.previous_state || 'Début') + ' → ' + event.next_state, dateLabel(event.timestamp) + ' · ' + event.reason);
}
async function loadReview() {
  const serial = ++reviewRequest;
  const missionId = $('reviewMission').value;
  review = null;
  $('transitionButton').disabled = true;
  for (const id of ['verificationList', 'blockers', 'verificationHistory', 'decisionHistory', 'workflowHistory', 'nextState']) $(id).replaceChildren();
  $('reviewState').textContent = missionId ? 'Chargement…' : 'Créez une mission pour examiner ses critères.';
  if (!missionId) return;
  const data = await request('/api/review/' + encodeURIComponent(missionId));
  if (serial !== reviewRequest) return;
  review = data;
  renderReview(data);
}
function bind(formId, path) {
  $(formId).addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button');
    const data = Object.fromEntries(new FormData(form).entries());
    const selection = {};
    if (formId === 'criterionForm') {
      data.expected_revision = snapshot.missions.find(m => m.id === data.mission_id)?.criteria_revision;
      selection.reviewMission = data.mission_id;
    }
    button.disabled = true;
    try {
      const result = await post(path, data);
      if (formId === 'missionForm') Object.assign(selection, { criterionMission: result.id, briefMission: result.id, reviewMission: result.id });
      if (formId === 'projectForm') selection.projectSelect = result.id;
      $('notice').textContent = 'Enregistrement effectué.';
      form.reset();
      await refresh(selection);
    } catch (error) { $('notice').textContent = 'Erreur : ' + error.message; }
    finally { button.disabled = false; }
  });
}
bind('projectForm', '/api/projects');
bind('missionForm', '/api/missions');
bind('criterionForm', '/api/criteria');
$('reviewMission').addEventListener('change', () => loadReview().catch(error => { $('notice').textContent = error.message; }));
$('reloadReview').addEventListener('click', () => refresh().catch(error => { $('notice').textContent = error.message; }));
$('transitionForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (!review) return;
  $('transitionButton').disabled = true;
  try {
    await post('/api/transition', { mission_id: review.mission.id, target: $('nextState').value,
      reason: event.currentTarget.elements.reason.value, expected_revision: review.mission.criteria_revision });
    $('notice').textContent = 'Étape enregistrée.';
    event.target.reset();
    await refresh();
  } catch (error) {
    $('notice').textContent = error.message;
    $('transitionButton').disabled = !review?.allowed_transitions.length;
  }
});
$('briefButton').addEventListener('click', async () => {
  const id = $('briefMission').value;
  if (!id) { $('notice').textContent = 'Créez une mission avant de générer une consigne.'; return; }
  try {
    const data = await request('/api/brief/' + encodeURIComponent(id));
    $('briefOutput').value = data.brief;
  } catch (error) { $('notice').textContent = error.message; }
});
$('copyBrief').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('briefOutput').value);
    $('notice').textContent = 'Consigne copiée. Collez-la dans Codex.';
  } catch (error) { $('notice').textContent = 'Copie impossible : sélectionnez et copiez manuellement la consigne.'; }
});
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('themeToggle').textContent = theme === 'light' ? 'Mode sombre' : 'Mode clair';
  $('themeToggle').setAttribute('aria-pressed', String(theme === 'light'));
}
let savedTheme;
try { savedTheme = localStorage.getItem('orchestra-theme'); } catch {}
setTheme(savedTheme === 'light' || savedTheme === 'dark' ? savedTheme : (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
$('themeToggle').addEventListener('click', () => {
  const theme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
  setTheme(theme);
  try { localStorage.setItem('orchestra-theme', theme); } catch {}
});
refresh().catch(error => { $('notice').textContent = 'Impossible de charger les données : ' + error.message; });
