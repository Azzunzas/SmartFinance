import { CurrencyPipe, DatePipe, DecimalPipe, PercentPipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, signal } from '@angular/core';
import { rxResource, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { NgxEchartsDirective } from 'ngx-echarts';
import type { EChartsCoreOption } from 'echarts/core';
import { finalize, switchMap, takeWhile, timer } from 'rxjs';

import { ConnectionsService } from '../../core/api/generated/connections/connections.service';
import { MetricsService } from '../../core/api/generated/metrics/metrics.service';
import { SyncService } from '../../core/api/generated/sync/sync.service';
import { TransactionsService } from '../../core/api/generated/transactions/transactions.service';
import { HealthStatusLabelPipe } from '../../shared/pipes/health-status-label.pipe';
import { PaymentMethodLabelPipe } from '../../shared/pipes/payment-method-label.pipe';

@Component({
  selector: 'app-overview',
  imports: [
    CurrencyPipe,
    DatePipe,
    DecimalPipe,
    HealthStatusLabelPipe,
    NgxEchartsDirective,
    PaymentMethodLabelPipe,
    PercentPipe,
    RouterLink,
  ],
  templateUrl: './overview.component.html',
  styleUrl: './overview.component.css',
})
export class OverviewComponent {
  private readonly metricsService = inject(MetricsService);
  private readonly connectionsService = inject(ConnectionsService);
  private readonly syncService = inject(SyncService);
  private readonly transactionsService = inject(TransactionsService);
  private readonly destroyRef = inject(DestroyRef);
  private syncPolling = false;

  protected readonly months = signal(6);
  protected readonly categoryPeriod = signal(this.currentPeriod());
  protected readonly syncing = signal(false);
  protected readonly syncMessage = signal<string | null>(null);
  protected readonly syncDetailsOpen = signal(false);

  protected readonly overview = rxResource({
    stream: () => this.metricsService.overviewApiMetricsOverviewGet(),
  });

  protected readonly upcoming = rxResource({
    stream: () => this.metricsService.upcomingApiMetricsUpcomingGet({ months: this.months() }),
  });

  protected readonly connections = rxResource({
    stream: () => this.connectionsService.listConnectionsApiConnectionsGet(),
  });

  protected readonly syncRuns = rxResource({
    stream: () => this.syncService.listRunsApiSyncRunsGet({ limit: 5, kind: 'MANUAL' }),
  });

  protected readonly recentTransactions = rxResource({
    stream: () => this.transactionsService.listAllApiTransactionsGet({ limit: 5 }),
  });

  protected readonly cashflow = rxResource({
    stream: () => this.metricsService.cashflowApiMetricsCashflowGet({ months: 6, order: 'asc' }),
  });

  protected readonly netWorthHistory = rxResource({
    stream: () => this.metricsService.networthApiMetricsNetworthGet({ days: 90 }),
  });

  protected readonly financialHealth = rxResource({
    stream: () => this.metricsService.healthApiMetricsHealthGet(),
  });

  protected readonly categorySpend = rxResource({
    params: () => this.categoryPeriod(),
    stream: ({ params }) =>
      this.metricsService.categoriesApiMetricsCategoriesGet({ period: params }),
  });

  protected readonly attentionConnections = computed(
    () => this.connections.value()?.filter((c) => c.consent_expiring || c.connection_stale) ?? [],
  );

  protected readonly bankAccounts = computed(
    () => this.overview.value()?.accounts.filter((a) => a.type === 'BANK') ?? [],
  );

  protected readonly creditAccounts = computed(
    () => this.overview.value()?.accounts.filter((a) => a.type === 'CREDIT') ?? [],
  );

  protected readonly bankTotal = computed(() =>
    this.bankAccounts().reduce((sum, account) => sum + Number(account.balance), 0),
  );

  protected readonly totalCommitted = computed(() =>
    (this.upcoming.value() ?? []).reduce((sum, month) => sum + Number(month.total), 0),
  );

  protected readonly categoryTotal = computed(() =>
    (this.categorySpend.value() ?? []).reduce((sum, category) => sum + Number(category.total), 0),
  );

  protected readonly hasCashflowData = computed(() =>
    (this.cashflow.value() ?? []).some(
      (month) => Number(month.total_in) !== 0 || Number(month.total_out) !== 0,
    ),
  );

  protected readonly netWorthPoints = computed(() => {
    const points = this.netWorthHistory.value() ?? [];
    const firstKnownIndex = points.findIndex((point) => Number(point.net_worth) !== 0);
    return firstKnownIndex === -1 ? [] : points.slice(firstKnownIndex);
  });

  protected readonly hasNetWorthData = computed(() => this.netWorthPoints().length > 0);

  protected readonly netWorthVariation = computed(() => {
    const points = this.netWorthPoints();
    if (points.length < 2) return null;
    return Number(points.at(-1)?.net_worth) - Number(points[0].net_worth);
  });

  protected readonly latestSync = computed(() => this.syncRuns.value()?.[0] ?? null);

  constructor() {
    this.syncService
      .syncStatusApiSyncStatusGet()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((status) => {
        if (status.running) this.pollSyncStatus();
      });
  }

  protected readonly upcomingChartOptions = computed<EChartsCoreOption>(() => {
    const months = this.upcoming.value() ?? [];

    return {
      grid: { left: 64, right: 16, top: 24, bottom: 32 },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: number | string) =>
          Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }),
      },
      xAxis: {
        type: 'category',
        data: months.map((m) => m.period),
        axisLine: { lineStyle: { color: this.cssVar('--color-border') } },
        axisLabel: { color: this.cssVar('--color-text-muted') },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: this.cssVar('--color-text-muted') },
        splitLine: { lineStyle: { color: this.cssVar('--color-border') } },
      },
      series: [
        {
          type: 'bar',
          data: months.map((m) => Number(m.total)),
          itemStyle: { color: this.cssVar('--color-negative'), borderRadius: [4, 4, 0, 0] },
        },
      ],
    };
  });

  protected readonly cashflowChartOptions = computed<EChartsCoreOption>(() => {
    const months = this.cashflow.value() ?? [];
    return {
      grid: { left: 68, right: 16, top: 36, bottom: 32 },
      legend: { top: 0, textStyle: { color: this.cssVar('--color-text-muted') } },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: number | string) => this.currency(value),
      },
      xAxis: {
        type: 'category',
        data: months.map((month) => this.periodLabel(month.period)),
        axisLine: { lineStyle: { color: this.cssVar('--color-border') } },
        axisLabel: { color: this.cssVar('--color-text-muted') },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: this.cssVar('--color-text-muted') },
        splitLine: { lineStyle: { color: this.cssVar('--color-border') } },
      },
      series: [
        {
          name: 'Receitas',
          type: 'bar',
          data: months.map((month) => Number(month.total_in)),
          itemStyle: { color: this.cssVar('--color-positive'), borderRadius: [3, 3, 0, 0] },
        },
        {
          name: 'Despesas',
          type: 'bar',
          data: months.map((month) => Number(month.total_out)),
          itemStyle: { color: this.cssVar('--color-negative'), borderRadius: [3, 3, 0, 0] },
        },
      ],
    };
  });

  protected readonly categoryChartOptions = computed<EChartsCoreOption>(() => {
    const categories = [...(this.categorySpend.value() ?? [])].sort(
      (a, b) => Number(a.total) - Number(b.total),
    );
    return {
      grid: { left: 112, right: 20, top: 8, bottom: 24 },
      tooltip: {
        trigger: 'item',
        renderMode: 'richText',
      },
      xAxis: {
        type: 'value',
        axisLabel: { color: this.cssVar('--color-text-muted') },
        splitLine: { lineStyle: { color: this.cssVar('--color-border') } },
      },
      yAxis: {
        type: 'category',
        data: categories.map((category) => category.name),
        axisLabel: { color: this.cssVar('--color-text-muted'), width: 96, overflow: 'truncate' },
        axisLine: { lineStyle: { color: this.cssVar('--color-border') } },
      },
      series: [
        {
          type: 'bar',
          data: categories.map((category) => ({
            name: category.name,
            value: Number(category.total),
            tooltip: {
              formatter: [
                `${category.name}: ${this.currency(category.total)}`,
                ...category.details.map(
                  (detail) => `${detail.name}: ${this.currency(detail.total)}`,
                ),
              ].join('\n'),
            },
          })),
          itemStyle: { color: this.cssVar('--color-accent'), borderRadius: [0, 4, 4, 0] },
        },
      ],
    };
  });

  protected readonly netWorthChartOptions = computed<EChartsCoreOption>(() => {
    const points = this.netWorthPoints();
    const accent = this.cssVar('--color-accent');
    return {
      grid: { left: 76, right: 20, top: 16, bottom: 32 },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: number | string) => this.currency(value),
      },
      xAxis: {
        type: 'category',
        data: points.map((point) => this.dateLabel(point.date)),
        axisLine: { lineStyle: { color: this.cssVar('--color-border') } },
        axisLabel: { color: this.cssVar('--color-text-muted'), hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: this.cssVar('--color-text-muted') },
        splitLine: { lineStyle: { color: this.cssVar('--color-border') } },
      },
      series: [
        {
          type: 'line',
          data: points.map((point) => Number(point.net_worth)),
          showSymbol: false,
          smooth: true,
          lineStyle: { color: accent, width: 2 },
          areaStyle: { color: `${accent}22` },
        },
      ],
    };
  });

  protected amountClass(value: string): 'positive' | 'negative' {
    return +value >= 0 ? 'positive' : 'negative';
  }

  protected variationClass(value: number): 'positive' | 'negative' {
    return value >= 0 ? 'positive' : 'negative';
  }

  protected syncStatusLabel(status: string): string {
    switch (status) {
      case 'SUCCESS':
        return 'Concluída';
      case 'PARTIAL':
        return 'Concluída parcialmente';
      case 'FAILED':
        return 'Falhou';
      default:
        return 'Em andamento';
    }
  }

  protected setCategoryPeriod(period: string): void {
    if (period) this.categoryPeriod.set(period);
  }

  protected startSync(): void {
    this.syncing.set(true);
    this.syncMessage.set(null);
    this.syncService.runSyncApiSyncRunPost().subscribe({
      next: () => this.pollSyncStatus(),
      error: (error: { status?: number }) => {
        if (error.status === 409) {
          this.pollSyncStatus();
        } else {
          this.syncing.set(false);
          this.syncMessage.set('Não foi possível iniciar a sincronização.');
        }
      },
    });
  }

  private pollSyncStatus(): void {
    if (this.syncPolling) return;
    this.syncPolling = true;
    this.syncing.set(true);
    timer(0, 2000)
      .pipe(
        switchMap(() => this.syncService.syncStatusApiSyncStatusGet()),
        takeWhile((status) => status.running, true),
        finalize(() => {
          this.syncPolling = false;
          this.syncing.set(false);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (status) => {
          if (!status.running) {
            this.syncMessage.set('Sincronização finalizada. Consulte o resultado abaixo.');
            this.reloadOverview();
          }
        },
        error: () => {
          this.syncMessage.set('Não foi possível acompanhar o estado da sincronização.');
        },
      });
  }

  private reloadOverview(): void {
    this.syncRuns.reload();
    this.overview.reload();
    this.connections.reload();
    this.cashflow.reload();
    this.netWorthHistory.reload();
    this.financialHealth.reload();
    this.categorySpend.reload();
    this.upcoming.reload();
    this.recentTransactions.reload();
  }

  private currency(value: number | string): string {
    return Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  private periodLabel(period: string): string {
    const [year, month] = period.split('-').map(Number);
    return new Intl.DateTimeFormat('pt-BR', { month: 'short', year: '2-digit' }).format(
      new Date(year, month - 1, 1),
    );
  }

  private dateLabel(date: string): string {
    return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit' }).format(
      new Date(`${date}T00:00:00`),
    );
  }

  private currentPeriod(): string {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  }

  private cssVar(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
}
