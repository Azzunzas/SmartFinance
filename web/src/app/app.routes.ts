import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'setup',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/setup.component').then((m) => m.SetupComponent),
  },
  {
    path: '',
    canActivateChild: [authGuard],
    children: [
      { path: '', redirectTo: 'overview', pathMatch: 'full' },
      {
        path: 'overview',
        loadComponent: () =>
          import('./features/overview/overview.component').then((m) => m.OverviewComponent),
      },
      {
        path: 'budget',
        loadChildren: () => import('./features/budget/budget.routes').then((m) => m.BUDGET_ROUTES),
      },
      {
        path: 'recurrences',
        loadChildren: () =>
          import('./features/recurrences/recurrences.routes').then((m) => m.RECURRENCES_ROUTES),
      },
      {
        path: 'transactions',
        loadComponent: () =>
          import('./features/transactions/transaction-list.component').then(
            (m) => m.TransactionListComponent,
          ),
      },
      {
        path: 'cards',
        loadComponent: () =>
          import('./features/cards/card-list.component').then((m) => m.CardListComponent),
      },
      {
        path: 'accounts',
        loadComponent: () =>
          import('./features/accounts/account-list.component').then((m) => m.AccountListComponent),
      },
      {
        path: 'goals',
        loadComponent: () =>
          import('./features/goals/goals.component').then((m) => m.GoalsComponent),
      },
    ],
  },
  { path: '**', redirectTo: 'overview' },
];
