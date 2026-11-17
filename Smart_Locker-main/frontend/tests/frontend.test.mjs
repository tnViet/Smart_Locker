import test from 'node:test';
import assert from 'node:assert/strict';
import {money,number,label,stateClass,apiError,fmtDuration,dateTime,onlyDate} from '../src/utils/format.js';

test('money and number format Vietnamese locale',()=>{
 assert.match(money(4500),/4\.500\s*đ/);
 assert.equal(number(12000),'12.000');
});
test('display correct compartment state',()=>{
 assert.equal(label('FREE'),'Còn trống');
 assert.equal(label('OCCUPIED'),'Đang sử dụng');
 assert.equal(stateClass('ERROR'),'danger');
 assert.equal(stateClass('FREE'),'success');
});
test('backend error message takes precedence',()=>{
 assert.equal(apiError({response:{data:{message:'Không có quyền'}},message:'network'}),'Không có quyền');
 assert.equal(apiError({message:'Network Error'}),'Network Error');
});
test('duration is displayed in minutes or hours',()=>{
 assert.equal(fmtDuration(5),'5 phút');
 assert.equal(fmtDuration(125),'2 giờ 5 phút');
});
test('invalid timestamps and empty values show placeholder',()=>{
 assert.equal(dateTime('not-a-date'),'—');
 assert.equal(onlyDate(null),'—');
});
