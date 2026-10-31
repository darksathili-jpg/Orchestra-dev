const { test, expect } = require('@playwright/test');

async function createMission(page) {
  const name = 'Mission preuves ' + Date.now();
  await page.goto('/');
  await page.locator('#projectForm input[name="name"]').fill('Projet ' + name);
  await page.getByRole('button', { name: '+ Ajouter le projet', exact: true }).click();
  await expect(page.locator('#projectsList')).toContainText(name);
  await page.locator('#missionForm input[name="title"]').fill(name);
  await page.getByRole('button', { name: '+ Créer une mission', exact: true }).click();
  await expect(page.locator('#reviewState')).toContainText(name);
  await page.locator('#criterionForm input[name="description"]').fill('Déplacement vérifié');
  await page.getByRole('button', { name: '+ Ajouter', exact: true }).click();
  await expect(page.locator('#verificationList .status')).toHaveText('NON_VÉRIFIÉ');
  return name;
}

async function verify(page, status, evidence) {
  await page.locator('#verificationList select').selectOption(status);
  await page.locator('#verificationList textarea').fill(evidence);
  const response = page.waitForResponse(r => r.url().endsWith('/api/verifications') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Enregistrer la vérification', exact: true }).click();
  expect((await response).status()).toBe(201);
  await expect(page.locator('#verificationList .status')).toHaveText(status);
  await expect(page.locator('#verificationList .proof')).toHaveText(evidence);
}

async function advance(page, state) {
  await page.locator('#nextState').selectOption(state);
  await page.locator('#transitionForm input[name="reason"]').fill('Étape constatée pendant la recette navigateur');
  await page.getByRole('button', { name: "Enregistrer l'étape", exact: true }).click();
  await expect(page.locator('#reviewState')).toContainText(state);
}

test('full evidence workflow ends with explicit authentication block', async ({ page }, testInfo) => {
  const name = await createMission(page);
  await expect(page.locator('#blockers')).toContainText('NON_VÉRIFIÉ');
  await verify(page, 'NON_CONFORME', 'Échec constaté : déplacement incorrect');
  await expect(page.locator('#blockers')).toContainText('NON_CONFORME');
  for (const state of ['SPÉCIFIÉE', 'PLAN_VALIDÉ', 'EN_EXÉCUTION', 'EN_VÉRIFICATION']) await advance(page, state);
  await page.locator('#nextState').selectOption('ATTENTE_VALIDATION_HUMAINE');
  await page.locator('#transitionForm input[name="reason"]').fill('Résultat encore non conforme');
  await page.getByRole('button', { name: "Enregistrer l'étape", exact: true }).click();
  await expect(page.locator('#notice')).toContainText('All criteria must be CONFORME');
  await verify(page, 'CONFORME', 'Rapport local : 12/12 contrôles réussis <img src=x onerror=alert(1)>');
  await expect(page.locator('#verificationList img')).toHaveCount(0);
  await expect(page.locator('#blockers')).toContainText('Tous les critères sont conformes');
  await advance(page, 'ATTENTE_VALIDATION_HUMAINE');
  await expect(page.locator('#approveButton')).toBeDisabled();
  await expect(page.locator('#approvalBlocker')).toContainText('Authentification humaine isolée indisponible');

  // A direct browser HTTP request does not turn this test into a human approver.
  const status = await page.evaluate(async () => {
    const id = document.querySelector('#reviewMission').value;
    const review = await (await fetch('/api/review/' + id)).json();
    const response = await fetch('/api/transition', { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Orchestra-Request': '1' },
      body: JSON.stringify({ mission_id: id, target: 'VALIDÉE', reason: 'Tentative non authentifiée', expected_revision: review.mission.criteria_revision }) });
    return response.status;
  });
  expect(status).toBe(401);
  await page.getByRole('button', { name: 'Actualiser la mission' }).click();
  await expect(page.locator('#decisionHistory')).toContainText('REFUS');
  await expect(page.locator('#verificationHistory')).toContainText('Échec constaté');
  await page.reload();
  await page.locator('#reviewMission').selectOption({ label: name });
  await expect(page.locator('#verificationList .proof')).toContainText('12/12');
  await expect(page.locator('#decisionHistory')).toContainText('Aucune identité authentifiée');
  await page.locator('#criterionMission').selectOption({ label: name });
  await page.locator('#criterionForm input[name="description"]').fill('Contrôle supplémentaire');
  await page.getByRole('button', { name: '+ Ajouter', exact: true }).click();
  await expect(page.locator('#reviewState')).toContainText('EN_VÉRIFICATION');
  await expect(page.locator('#blockers')).toContainText('Contrôle supplémentaire');
  await page.screenshot({ path: testInfo.outputPath('evidence-workflow.png'), fullPage: true });
});

for (const theme of ['light', 'dark']) {
  test('readable evidence controls in ' + theme + ' mode', async ({ page }, testInfo) => {
    await page.emulateMedia({ colorScheme: theme });
    await createMission(page);
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    const ratios = await page.locator('input, select, textarea, button').evaluateAll(nodes => {
      const luminance = color => {
        const values = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => {
          v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
        });
        return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
      };
      return nodes.filter(node => node.getClientRects().length).map(node => {
        const style = getComputedStyle(node);
        const foreground = luminance(style.color), background = luminance(style.backgroundColor);
        return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
      });
    });
    expect(Math.min(...ratios)).toBeGreaterThanOrEqual(4.5);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.locator('#review').scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('evidence-' + theme + '.png'), fullPage: true });
    await page.locator('#themeToggle').click();
    const changed = theme === 'light' ? 'dark' : 'light';
    await expect(page.locator('html')).toHaveAttribute('data-theme', changed);
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', changed);
  });
}

test('stale browser tab retains evidence draft and cannot overwrite a newer result', async ({ page }) => {
  await createMission(page);
  await page.locator('#verificationList textarea').fill('Brouillon conservé');
  const code = await page.evaluate(async () => {
    const id = document.querySelector('#reviewMission').value;
    const data = await (await fetch('/api/review/' + id)).json();
    const response = await fetch('/api/verifications', { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Orchestra-Request': '1' },
      body: JSON.stringify({ criterion_id: data.criteria[0].id, status: 'CONFORME', evidence: 'Résultat concurrent', expected_revision: data.mission.criteria_revision }) });
    return response.status;
  });
  expect(code).toBe(201);
  await page.getByRole('button', { name: 'Enregistrer la vérification', exact: true }).click();
  await expect(page.locator('#notice')).toContainText('Les critères ont changé');
  await expect(page.locator('#verificationList textarea')).toHaveValue('Brouillon conservé');
  await page.getByRole('button', { name: 'Actualiser la mission' }).click();
  await expect(page.locator('#verificationList .proof')).toHaveText('Résultat concurrent');
});
