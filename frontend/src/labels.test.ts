import {describe,it,expect} from 'vitest'
import {statusLabel,initials} from './types'

describe('etapy i inicjały',()=>{
 it('kwerenda pokazuje liczbę dni przedłużenia',()=>{
  expect(statusLabel({status:'kwerenda',extension_days:30})).toBe('Kwerenda +30 dni')
  expect(statusLabel({status:'zarejestrowany'})).toBe('Brak działań')
  expect(statusLabel({status:'zakonczony'})).toBe('Odpowiedź wysłana')
 })
 it('inicjały z imienia i nazwiska',()=>{
  expect(initials('Jan Maria Kowalski')).toBe('JK')
  expect(initials('MS')).toBe('MS')
  expect(initials('')).toBe('—')
 })
})
