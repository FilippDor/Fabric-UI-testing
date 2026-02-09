import { test, expect, chromium, Browser } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import {
  getAccessToken,
  getReportEmbedToken,
  createReportEmbedInfo,
  getAPIEndpoints
} from '../helper-functions/token-helpers';
import { readJSONFilesFromFolder } from '../helper-functions/file-reader';
import { logToConsole } from '../helper-functions/logging';

/* -------------------- ENV -------------------- */
const CLIENT_ID = process.env.SP_CLIENT_ID!;
const CLIENT_SECRET = process.env.SP_CLIENT_SECRET!;
const TENANT_ID = process.env.SP_TENANT_ID!;
const ENVIRONMENT = process.env.ENVIRONMENT || 'prod';

if (!CLIENT_ID || !CLIENT_SECRET || !TENANT_ID) {
  throw new Error('Missing required environment variables.');
}

/* -------------------- PATHS -------------------- */
const TEST_RESULTS_DIR = path.resolve(__dirname, '../test-results');
fs.mkdirSync(TEST_RESULTS_DIR, { recursive: true });

const reportsPath = path.resolve(__dirname, '../metadata/reports');
const reports = readJSONFilesFromFolder(reportsPath).filter(
  (r): r is NonNullable<typeof r> => r != null
);
if (reports.length === 0) throw new Error(`No reports found in ${reportsPath}`);

const endpoints = getAPIEndpoints(ENVIRONMENT);

/* -------------------- PLAYWRIGHT SETUP -------------------- */
test.setTimeout(900_000);
test.describe.configure({ mode: 'parallel' });

let browser: Browser;
let accessToken: string;

test.beforeAll(async () => {
  browser = await chromium.launch({ headless: true });
  accessToken = await getAccessToken({
    clientId: CLIENT_ID,
    clientSecret: CLIENT_SECRET,
    tenantId: TENANT_ID,
    environment: ENVIRONMENT
  });
});

test.afterAll(async () => {
  await browser.close();
});

/* -------------------- TESTS -------------------- */
test.describe('PBI_Rendering_Validation', () => {
  reports.forEach((report) => {
    test(`Validating_Rendering: ${report.Name} (${report.Id})`, async () => {
      const startNodeTime = Date.now();
      const context = await browser.newContext();
      const page = await context.newPage();

      await page.goto('about:blank');
      await page.addScriptTag({
        url: 'https://cdnjs.cloudflare.com/ajax/libs/powerbi-client/2.23.1/powerbi.min.js'
      });

      const embedInfo = createReportEmbedInfo(report);
      const embedToken = await getReportEmbedToken(embedInfo, endpoints, accessToken);

      const reportInfo = {
        reportId: embedInfo.reportId,
        embedUrl: report.EmbedUrl,
        embedToken,
        workspaceId: report.WorkspaceId // REQUIRED
      };

      /* -------------------- PHASE 1: Scan Pages & Capture Errors -------------------- */
      const scanResults = await page.evaluate(async (reportInfo) => {
      const t0 = performance.now();
      const pbi = (window as any)['powerbi-client'];
      const models = pbi.models;

      const container = document.createElement('div');
      container.id = 'powerbi-container';
      container.style.width = '1200px';
      container.style.height = '800px';
      document.body.appendChild(container);

      const powerbi = new pbi.service.Service(
        pbi.factories.hpmFactory,
        pbi.factories.wpmpFactory,
        pbi.factories.routerFactory
      );

      const report = powerbi.embed(container, {
        type: 'report',
        id: reportInfo.reportId,
        embedUrl: reportInfo.embedUrl,
        accessToken: reportInfo.embedToken,
        tokenType: models.TokenType.Embed,
        permissions: models.Permissions.Read,
        viewMode: models.ViewMode.View,
        settings: { visualRenderedEvents: true }
      });

      const reportLoadTime: number = await new Promise(res =>
        report.on('loaded', () => res(performance.now()))
      );

      const pages = await report.getPages();

      const pageErrors: Record<string, Record<string, string>> = {};
      const pagesToScreenshot: { name: string; serviceUrl: string; embedUrl: string;}[] = [];
      const pageTimings: Record<string, { start: number; end: number; duration: number }> = {};

      for (const pageObj of pages) {
        const pageStart = performance.now();
        const pageName = pageObj.name;

        pageErrors[pageName] = {};
        let errorDetected = false;
        const visuals = await pageObj.getVisuals();
        let renderedVisuals = 0;  

        const onError = (event: any) => {
          const visualId =
            event?.detail?.visualName ||
            event?.detail?.visualId ||
            'unknown';
          pageErrors[pageName][visualId] =
            event?.detail?.message || 'Unknown Power BI error';
          errorDetected = true;
        };

        const onRendered = () => {
          renderedVisuals++;
        };

        report.on('error', onError);
        report.on('visualRendered', onRendered);

        await pageObj.setActive();

        // Wait for render OR error OR timeout
        await Promise.race([
          new Promise<void>((resolve) => {
            const check = () => {
              if (errorDetected || renderedVisuals >= visuals.length) {
                resolve();
              } else {
                setTimeout(check, 1000);
              }
            };
            check();
          }),
          new Promise<void>(resolve => setTimeout(resolve, 15000))
        ]);


        report.off('error', onError);
        report.off('visualRendered', onRendered);

        if (Object.keys(pageErrors[pageName]).length > 0) {
          pagesToScreenshot.push({
            name: pageName,

            serviceUrl: `https://app.powerbi.com/groups/${reportInfo.workspaceId}/reports/${reportInfo.reportId}/${pageName}`,

            embedUrl: `https://app.powerbi.com/reportEmbed?reportId=${reportInfo.reportId}&pageName=${pageName}`
          });

        }

        const pageEnd = performance.now();
        pageTimings[pageName] = {
          start: pageStart,
          end: pageEnd,
          duration: pageEnd - pageStart
        };
      }

      return {
        pageErrors,
        pagesToScreenshot,
        pageTimings,
        reportLoadTime,
        totalDuration: performance.now() - t0
      };
    }, reportInfo);


      /* -------------------- PHASE 2: Take Screenshots -------------------- */
      for (const pageObj of scanResults.pagesToScreenshot) {
        await page.evaluate(async (pageName) => {
          const report = (window as any).powerbi.get(document.querySelector('#powerbi-container'));
          const pages = await report.getPages();
          const target = pages.find((p: any) => p.name === pageName);
          if (target) await target.setActive();
        }, pageObj.name);

        await page.waitForTimeout(800); // small wait for rendering
        const screenshotBuffer = await page.locator('#powerbi-container').screenshot();
        test.info().attach(`${pageObj.name}-screenshot`, {
          body: screenshotBuffer,
          contentType: 'image/png'
        });
      }

      /* -------------------- SAVE RESULTS JSON -------------------- */
      const endNodeTime = Date.now();
      const resultFile = path.join(TEST_RESULTS_DIR, `${report.Id}_result.json`);
      fs.writeFileSync(resultFile, JSON.stringify({
        reportId: report.Id,
        reportName: report.Name,
        environment: ENVIRONMENT,
        pageErrors: scanResults.pageErrors,
        pagesToScreenshot: scanResults.pagesToScreenshot,
        pageTimings: scanResults.pageTimings,
        reportLoadTime: scanResults.reportLoadTime,
        totalDuration: scanResults.totalDuration,
        nodeDuration: endNodeTime - startNodeTime
      }, null, 2));
      logToConsole(`[INFO] Results saved: ${resultFile}`, true);

      // Soft assertion
      const failedPages = Object.entries(scanResults.pageErrors)
        .filter(([_, visualErrors]) => Object.keys(visualErrors).length > 0);
      expect.soft(failedPages.length).toBe(0);

      if (failedPages.length > 0) {
        console.log('Failed pages:', failedPages.map(([name]) => name));
      }

      await context.close();
    });
  });
});