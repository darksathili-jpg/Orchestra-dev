const { test, expect } = require('@playwright/test');

test('dashboard, mission brief and persistence', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Tableau de bord' })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Préparer une mission pour Codex/ })).toBeVisible();

  const suffix = Date.now().toString();
  const project = 'Microduck E2E ' + suffix;
  const mission = 'Déplacements vérifiables ' + suffix;
  const criterion = 'Une instruction entraîne une case ' + suffix;

  await page.locator('#projectForm input[name="name"]').fill(project);
  await page.locator('#projectForm input[name="repo"]').fill('darksathili-jpg/agents_ia');
  await page.getByRole('button', { name: '+ Ajouter le projet' }).click();
  await expect(page.locator('#projectsList')).toContainText(project);

  await page.locator('#projectSelect').selectOption({ label: project });
  await page.locator('#missionForm input[name="title"]').fill(mission);
  await page.getByRole('button', { name: '+ Créer une mission' }).click();
  await expect(page.locator('#missionsList')).toContainText(mission);

  await page.locator('#criterionMission').selectOption({ label: mission });
  await page.locator('#criterionForm input[name="description"]').fill(criterion);
  await page.getByRole('button', { name: '+ Ajouter' }).click();
  await expect(page.locator('#criteriaList')).toContainText(criterion);
  await expect(page.locator('#criteriaList')).toContainText('NON_VÉRIFIÉ');

  await page.locator('#briefMission').selectOption({ label: mission });
  await page.getByRole('button', { name: 'Générer la consigne' }).click();
  await expect(page.locator('#briefOutput')).toHaveValue(new RegExp(criterion));
  await expect(page.locator('#briefOutput')).toHaveValue(/sans modifier les fichiers/);
  await page.screenshot({ path: 'test-results/command-center.png', fullPage: true });

  await page.reload();
  await expect(page.locator('#projectsList')).toContainText(project);
  await expect(page.locator('#missionsList')).toContainText(mission);
  await expect(page.locator('#criteriaList')).toContainText(criterion);
});

test('narrow viewport keeps agent panel usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Préparer une mission pour Codex/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Générer la consigne' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});
