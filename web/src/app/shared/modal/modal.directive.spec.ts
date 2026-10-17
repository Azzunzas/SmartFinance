import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ModalDirective } from './modal.directive';

@Component({
  imports: [ModalDirective],
  template: `
    <button id="trigger" type="button" (click)="open.set(true)">Abrir</button>
    <p id="background">Conteúdo de fundo</p>
    @if (open()) {
      <div class="backdrop">
        <section appModal role="dialog" (dismissed)="open.set(false)">
          <button id="first" type="button">Primeiro</button>
          <button id="last" type="button">Último</button>
        </section>
      </div>
    }
  `,
})
class ModalHostComponent {
  readonly open = signal(false);
}

describe('ModalDirective', () => {
  let fixture: ComponentFixture<ModalHostComponent>;
  let root: HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [ModalHostComponent] }).compileComponents();
    fixture = TestBed.createComponent(ModalHostComponent);
    root = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  });

  async function openModal(): Promise<void> {
    root.querySelector<HTMLButtonElement>('#trigger')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
  }

  it('moves focus into the modal and makes the background inert', async () => {
    await openModal();

    expect(document.activeElement).toBe(root.querySelector('#first'));
    expect(root.querySelector<HTMLElement>('#trigger')!.inert).toBe(true);
    expect(root.querySelector<HTMLElement>('#background')!.inert).toBe(true);
  });

  it('keeps keyboard focus inside the modal', async () => {
    await openModal();
    const first = root.querySelector<HTMLButtonElement>('#first')!;
    const last = root.querySelector<HTMLButtonElement>('#last')!;
    last.focus();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(first);

    first.focus();
    document.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }),
    );
    expect(document.activeElement).toBe(last);
  });

  it('closes with Escape and restores the background and trigger focus', async () => {
    const trigger = root.querySelector<HTMLButtonElement>('#trigger')!;
    trigger.focus();
    await openModal();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    fixture.detectChanges();

    expect(root.querySelector('[role="dialog"]')).toBeNull();
    expect(trigger.inert).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });
});
