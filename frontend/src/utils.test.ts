import {describe,it,expect} from 'vitest'
import {textRange,caseYear} from './utils'
describe('registry year',()=>{
 it('uses receipt dates for arbitrary and historical references',()=>{
  expect(caseYear({received:'2026-11-22'})).toBe('2026')
  expect(caseYear({received:'2025-01-01'})).toBe('2025')
 })
})
describe('PII selection coordinates',()=>{
 it('keeps the correct span after emoji and Polish characters',()=>{
  const source='😀 Zażółć. Ewa Góra — kontakt.'
  const range=textRange(source,'Ewa Góra')!
  expect(Array.from(source).slice(range.start,range.end).join('')).toBe('Ewa Góra')
  expect(range).toEqual({start:10,end:18})
 })
 it('rejects empty and missing selections',()=>{expect(textRange('abc','')).toBeNull();expect(textRange('abc','def')).toBeNull()})
})
