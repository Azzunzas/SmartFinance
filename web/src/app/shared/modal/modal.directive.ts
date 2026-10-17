import {
  AfterViewInit,
  Directive,
  ElementRef,
  HostListener,
  inject,
  OnDestroy,
  output,
} from '@angular/core';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

@Directive({
  selector: '[appModal]',
  host: { tabindex: '-1' },
})
export class ModalDirective implements AfterViewInit, OnDestroy {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly previouslyFocused = document.activeElement as HTMLElement | null;
  private readonly backgroundState = new Map<HTMLElement, boolean>();
  private destroyed = false;

  readonly dismissed = output<void>();

  ngAfterViewInit(): void {
    this.disableBackground();
    queueMicrotask(() => {
      if (this.destroyed) return;
      const initialFocus = this.focusableElements()[0] ?? this.host;
      initialFocus.focus();
    });
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    for (const [element, wasInert] of this.backgroundState) element.inert = wasInert;
    this.previouslyFocused?.focus();
  }

  @HostListener('document:keydown', ['$event'])
  protected handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      this.dismissed.emit();
      return;
    }

    if (event.key !== 'Tab') return;
    const focusable = this.focusableElements();
    if (focusable.length === 0) {
      event.preventDefault();
      this.host.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable.at(-1)!;
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !this.host.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !this.host.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  }

  private focusableElements(): HTMLElement[] {
    return [...this.host.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)].filter(
      (element) => !element.hidden && element.getAttribute('aria-hidden') !== 'true',
    );
  }

  private disableBackground(): void {
    let current: HTMLElement = this.host;
    while (current.parentElement && current.parentElement !== document.body) {
      const parent = current.parentElement;
      for (const sibling of parent.children) {
        if (
          sibling === current ||
          sibling.contains(this.host) ||
          !(sibling instanceof HTMLElement)
        ) {
          continue;
        }
        if (!this.backgroundState.has(sibling)) {
          this.backgroundState.set(sibling, Boolean(sibling.inert));
        }
        sibling.inert = true;
      }
      current = parent;
    }
  }
}
